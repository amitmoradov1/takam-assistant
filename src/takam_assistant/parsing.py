"""פירוק מסמך תכ"ם לסעיפים.

הוראות תכ"ם בנויות במבנה היררכי אחיד: סעיפים ממוספרים (1. מבוא, 2. הנחיות
לביצוע, 2.1, 2.3.1 וכן הלאה) ונספחים ("נספח א – הגדרות") שבהם המספור מתחיל
מחדש. הפירוק לסעיפים הוא מה שמאפשר לנו לצטט מקור מדויק ("הוראה 7.6.1,
סעיף 2.3.1" או "נספח ג, סעיף 2") ולא רק "איפשהו במסמך".

כללי הזיהוי (מכוילים מול מסמכים אמיתיים מהאתר, ראו docx_extract.py):
- מספר רב-רכיבי ("2.3", "2.3.1") פותח סעיף, עם או בלי נקודה בסופו.
- מספר בודד פותח סעיף רק עם נקודה ("1. מבוא") — כדי ששורת תוכן שמתחילה
  במספר ("30 ימים...") לא תזוהה בטעות ככותרת.
- בתוך נספח, מספרי הסעיפים מקבלים את אות הנספח ("ג.2") כי המספור בנספחים
  מתחיל מחדש ואחרת הציטוט היה דו-משמעי.
- שורה ממוספרת ארוכה היא סעיף שתוכנו הוא השורה עצמה (בהוראות אמיתיות רוב
  הסעיפים הם משפט מלא, לא כותרת).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Section:
    number: str          # "3.1.2", "ג.2" בנספח ("" לטקסט ללא מספור)
    title: str
    content: str


@dataclass
class TakamDocument:
    doc_id: str
    title: str
    instruction_number: str   # מספר ההוראה, למשל "7.6.1"
    chapter: str              # שם הפרק, למשל "התקשרויות ורכישות"
    url: str
    effective_date: str
    text: str
    file_url: str = ""         # קישור ישיר לקובץ ההוראה (הנוסח המחייב)
    sections: list[Section] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: dict) -> "TakamDocument":
        doc = cls(
            doc_id=raw["doc_id"],
            title=raw["title"],
            instruction_number=raw.get("instruction_number", ""),
            chapter=raw.get("chapter", ""),
            url=raw.get("url", ""),
            effective_date=raw.get("effective_date", ""),
            text=raw["text"],
            file_url=raw.get("file_url", ""),
        )
        doc.sections = parse_sections(doc.text)
        return doc


# שורת סעיף: מספר רב-רכיבי (נקודה אופציונלית בסוף) או מספר בודד עם נקודה,
# ואחריו טקסט. מספר בודד ללא נקודה ("30 ימים") אינו כותרת — ראו docstring.
_HEADING_RE = re.compile(
    r"^\s*(?:(\d{1,2}(?:\.\d{1,2}){1,2})\.?|(\d{1,2})\.)\s+(\S.*?)\s*$"
)

# פתיחת נספח: "נספח א – הגדרות", "נספח ב:", "נספח ג"
_APPENDIX_RE = re.compile(r"^\s*נספח\s+([א-ת])\b\s*(?:[-–—:]\s*(.*?))?\s*$")

# כותרת סעיף קצרה (ללא תוכן) לעומת סעיף שהוא משפט שלם
_MAX_TITLE_CHARS = 80


def parse_sections(text: str) -> list[Section]:
    sections: list[Section] = []
    current = Section(number="", title="", content="")
    appendix = ""  # אות הנספח הנוכחי ("" בגוף ההוראה)

    def push() -> None:
        if current.content.strip() or current.title:
            sections.append(current)

    for line in text.splitlines():
        appendix_match = _APPENDIX_RE.match(line)
        if appendix_match:
            push()
            appendix = appendix_match.group(1)
            title = (appendix_match.group(2) or "").strip()
            # מספר הסעיף של כותרת הנספח הוא האות עצמה — כך סעיפי הנספח
            # ("א.3") משתרשרים אליה בפירורי-הלחם של ה-chunking
            current = Section(number=appendix,
                              title=f"נספח {appendix}" + (f" – {title}" if title else ""),
                              content="")
            continue

        heading_match = _HEADING_RE.match(line)
        if heading_match:
            push()
            number = heading_match.group(1) or heading_match.group(2)
            if appendix:
                number = f"{appendix}.{number}"
            rest = heading_match.group(3).strip()
            if len(rest) <= _MAX_TITLE_CHARS:
                current = Section(number=number, title=rest, content="")
            else:  # סעיף-משפט: המספר מזהה אותו, הטקסט הוא התוכן
                current = Section(number=number, title="", content=rest + "\n")
            continue

        current.content += line + "\n"

    push()

    # מסמך ללא מספור בכלל — סעיף יחיד עם כל הטקסט
    if not sections:
        sections = [Section(number="", title="", content=text)]
    return sections
