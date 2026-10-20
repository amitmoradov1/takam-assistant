"""חילוץ טקסט מקובצי DOCX של הוראות תכ"ם, כולל שחזור מספור הסעיפים.

הוראות התכ"ם מתפרסמות באתר כקובצי Word. הבעיה: מספור הסעיפים (1, 2.3,
2.3.1...) הוא מספור אוטומטי של Word — הוא לא קיים כטקסט בתוך הפסקאות,
אלא מוגדר הצהרתית ב-numbering.xml ומוצמד לפסקאות דרך numPr או דרך סגנון.
חילוץ נאיבי (כמו pypdf ל-PDF) היה מאבד את המספור — ובלעדיו אין ציטוט
ברמת סעיף, שהוא ליבת המוצר.

לכן אנחנו משחזרים את המספור כפי ש-Word היה מציג אותו:
1. numbering.xml: numId → abstractNum → לכל רמה (ilvl): פורמט (decimal/
   bullet), תבנית (lvlText כמו "%1.%2."), וערך התחלה.
2. styles.xml: סגנונות פסקה שנושאים numPr (כך ממוספרות רוב הכותרות).
3. מעבר סדרתי על פסקאות המסמך עם מוני-רמות: פסקה ממוספרת מקדמת את המונה
   ברמתה ומאפסת את הרמות העמוקות ממנה — בדיוק כמו Word.

הפלט: טקסט שבו כל פסקה ממוספרת מתחילה במספרה ("2.3.1 ועדת המכרזים..."),
מוכן לפירוק סעיפים ב-parsing.py.

מגבלה מוצהרת (ראו README): טבלאות נשטחות לרצף פסקאות לפי סדר התאים,
ומספור מסוג bullet/אותיות מושמט בכוונה (אינו משמש לציטוט).
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from io import BytesIO

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# פורמטים שמייצרים מספור עשרוני בר-ציטוט; bullet/אותיות/רומיות מושמטים
_NUMERIC_FORMATS = {"decimal"}

_PLACEHOLDER_RE = re.compile(r"%(\d)")

# שאריות של שדות REF שבורים שקיימות במסמכי המקור עצמם (גם Word מציג שם
# "Error!"): מזהה OLE הקסדצימלי של היעד + הודעת השגיאה של Word
_FIELD_GARBAGE_RE = re.compile(
    r"(?:08)?D0C9EA79F9BACE11[0-9A-Fa-f]+|Error! Reference source not found\.?"
)
_MULTISPACE_RE = re.compile(r"[ \t]{2,}")


def _clean_paragraph(text: str) -> str:
    text = _FIELD_GARBAGE_RE.sub(" ", text)
    return _MULTISPACE_RE.sub(" ", text).strip()


@dataclass
class _Level:
    num_fmt: str      # "decimal" / "bullet" / ...
    lvl_text: str     # תבנית, למשל "%1.%2."
    start: int


def _attr(element: ET.Element | None, name: str) -> str | None:
    return element.get(W + name) if element is not None else None


def _parse_numbering(data: bytes) -> dict[str, dict[int, _Level]]:
    """numId → {ilvl → Level}, אחרי פתרון ההפניה numId→abstractNum."""
    root = ET.fromstring(data)

    abstract: dict[str, dict[int, _Level]] = {}
    for abstract_num in root.iter(W + "abstractNum"):
        levels: dict[int, _Level] = {}
        for lvl in abstract_num.iter(W + "lvl"):
            ilvl = int(lvl.get(W + "ilvl", "0"))
            start = _attr(lvl.find(W + "start"), "val")
            levels[ilvl] = _Level(
                num_fmt=_attr(lvl.find(W + "numFmt"), "val") or "none",
                lvl_text=_attr(lvl.find(W + "lvlText"), "val") or "",
                start=int(start) if start else 1,
            )
        abstract[abstract_num.get(W + "abstractNumId", "")] = levels

    numbering: dict[str, dict[int, _Level]] = {}
    for num in root.iter(W + "num"):
        abstract_id = _attr(num.find(W + "abstractNumId"), "val")
        if abstract_id in abstract:
            numbering[num.get(W + "numId", "")] = abstract[abstract_id]
    return numbering


def _parse_style_numbering(data: bytes) -> dict[str, tuple[str | None, int]]:
    """styleId → (numId, ilvl) עבור סגנונות שמגדירים מספור."""
    root = ET.fromstring(data)
    styles: dict[str, tuple[str | None, int]] = {}
    for style in root.iter(W + "style"):
        num_pr = style.find(f"{W}pPr/{W}numPr")
        if num_pr is None:
            continue
        num_id = _attr(num_pr.find(W + "numId"), "val")
        ilvl = _attr(num_pr.find(W + "ilvl"), "val")
        styles[style.get(W + "styleId", "")] = (num_id, int(ilvl) if ilvl else 0)
    return styles


class _NumberingState:
    """מוני רמות לכל numId — משחזר את התנהגות Word: קידום ברמה הנוכחית
    מאפס את כל הרמות העמוקות ממנה.

    המונים מנוהלים לכל numId בנפרד (ולא לכל abstractNum): כך רשימת
    ההגדרות בנספח, שמצביעה ל-numId אחר, מתחילה מ-1 מחדש — בדיוק כפי
    ש-Word מציג אותה. parsing.py מוסיף לסעיפי נספח את אות הנספח כדי
    שהמספור החוזר לא ייצר ציטוט דו-משמעי."""

    def __init__(self, numbering: dict[str, dict[int, _Level]]) -> None:
        self._numbering = numbering
        self._counters: dict[str, dict[int, int]] = {}

    def advance(self, num_id: str, ilvl: int) -> str | None:
        """מחזיר את המספר המשוחזר ("2.3.1") או None אם הרמה אינה עשרונית."""
        levels = self._numbering.get(num_id)
        if not levels or ilvl not in levels:
            return None
        level = levels[ilvl]
        if level.num_fmt not in _NUMERIC_FORMATS or "%" not in level.lvl_text:
            return None

        counters = self._counters.setdefault(num_id, {})
        counters[ilvl] = counters.get(ilvl, level.start - 1) + 1
        for deeper in [d for d in counters if d > ilvl]:
            del counters[deeper]

        def fill(match: re.Match) -> str:
            lvl_index = int(match.group(1)) - 1
            lvl_def = levels.get(lvl_index)
            default = lvl_def.start if lvl_def else 1
            return str(counters.get(lvl_index, default))

        number = _PLACEHOLDER_RE.sub(fill, level.lvl_text)
        return number.strip().rstrip(".")


def extract_docx_text(data: bytes) -> str:
    """טקסט מלא של המסמך, פסקה לשורה, עם מספור סעיפים משוחזר בראש כל
    פסקה ממוספרת: "2.3. ועדת המכרזים תנמק..."."""
    with zipfile.ZipFile(BytesIO(data)) as archive:
        document = archive.read("word/document.xml")
        names = set(archive.namelist())
        numbering = (_parse_numbering(archive.read("word/numbering.xml"))
                     if "word/numbering.xml" in names else {})
        styles = (_parse_style_numbering(archive.read("word/styles.xml"))
                  if "word/styles.xml" in names else {})

    state = _NumberingState(numbering)
    lines: list[str] = []
    for paragraph in ET.fromstring(document).iter(W + "p"):
        text = _clean_paragraph(
            "".join(t.text or "" for t in paragraph.iter(W + "t")))
        if not text:
            continue

        p_pr = paragraph.find(W + "pPr")
        num_pr = p_pr.find(W + "numPr") if p_pr is not None else None
        num_id: str | None = None
        ilvl = 0
        if num_pr is not None:  # מספור ישיר על הפסקה גובר על הסגנון
            num_id = _attr(num_pr.find(W + "numId"), "val")
            ilvl_val = _attr(num_pr.find(W + "ilvl"), "val")
            ilvl = int(ilvl_val) if ilvl_val else 0
        if num_id is None and p_pr is not None:
            style_id = _attr(p_pr.find(W + "pStyle"), "val")
            if style_id in styles:
                num_id, ilvl = styles[style_id]

        number = state.advance(num_id, ilvl) if num_id else None
        lines.append(f"{number}. {text}" if number else text)

    return "\n".join(lines)
