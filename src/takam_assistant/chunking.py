"""חלוקת מסמכים לקטעים (chunks) לאינדוקס ואחזור.

כל קטע נושא את מלוא המטא-דאטה שלו (הוראה, סעיף, כותרת, קישור) כדי שהתשובה
הסופית תוכל לצטט מקור מדויק. קטעים נחתכים על גבולות סעיפים — לעולם לא באמצע
סעיף קצר — וסעיפים ארוכים נחתכים על גבולות משפטים עם חפיפה קלה.

פירורי-לחם (breadcrumbs): בהוראות האמיתיות סעיף הוא לרוב משפט בודד
("2.1.1 משרד יערוך התקשרות...") שמילות ההקשר שלו — "עדיפות המכרז הפומבי" —
נמצאות רק בכותרות האב (2.1, 2). לכן כל קטע מקבל בראשו את שרשרת כותרות
האב שלו: זה משפר מהותית גם את האחזור (המילים האלה נכנסות לאינדקס) וגם את
ההקשר שהמודל רואה.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict

from .parsing import TakamDocument

MAX_CHUNK_CHARS = 1100
OVERLAP_SENTENCES = 1

_SENTENCE_RE = re.compile(r"(?<=[.;:!?])\s+")
# מספר סעיף בתוך נספח: "ג" או "ג.2"
_APPENDIX_SECTION_RE = re.compile(r"^([א-ת])(?:\.(.+))?$")
# כותרת הסעיף הקבוע בהוראות תכ"ם שמרכז את רשימת ההפניות
REFERENCE_LIST_TITLE = "מסמכים ישימים"


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    instruction_number: str
    doc_title: str
    chapter: str
    section_number: str
    section_title: str
    url: str
    effective_date: str
    text: str
    # משקל אחזור: קטעים מסעיפי "מסמכים ישימים" (רשימות הפניה שמצטטות את
    # כותרות ההוראות האחרות) מקבלים משקל מופחת — הם כמעט-העתק של שאילתות
    # ("אילו כללים חלים על מאגר מציעים") בלי לשאת תשובה מהותית
    weight: float = 1.0

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def citation(self) -> str:
        """תווית ציטוט קריאה: "הוראה 7.6.1 (פטור מחובת המכרז), סעיף 2.3"
        או, לסעיפי נספח, "... נספח ג, סעיף 2"."""
        label = f'הוראה {self.instruction_number} ({self.doc_title})'
        appendix = _APPENDIX_SECTION_RE.match(self.section_number or "")
        if appendix:
            label += f", נספח {appendix.group(1)}"
            if appendix.group(2):
                label += f", סעיף {appendix.group(2)}"
        elif self.section_number:
            label += f", סעיף {self.section_number}"
        return label


def _split_long_text(text: str) -> list[str]:
    sentences = [s.strip() for s in _SENTENCE_RE.split(text) if s.strip()]
    parts: list[str] = []
    current: list[str] = []
    length = 0
    for sentence in sentences:
        if length + len(sentence) > MAX_CHUNK_CHARS and current:
            parts.append(" ".join(current))
            current = current[-OVERLAP_SENTENCES:]  # חפיפה לשמירת הקשר
            length = sum(len(s) for s in current)
        current.append(sentence)
        length += len(sentence)
    if current:
        parts.append(" ".join(current))
    return parts or [text]


def _parent_number(number: str) -> str:
    """ "2.3.1" → "2.3" → "2" → "" (עובד גם לסעיפי נספח: "ג.2" → "ג")."""
    return number.rsplit(".", 1)[0] if "." in number else ""


def _breadcrumbs(sections) -> dict[str, str]:
    """מספר סעיף → שרשרת כותרות האב שלו ("הנחיות לביצוע › עדיפות המכרז...")."""
    titles = {s.number: s.title for s in sections if s.number and s.title}
    crumbs: dict[str, str] = {}
    for section in sections:
        chain: list[str] = []
        parent = _parent_number(section.number)
        while parent:
            if parent in titles:
                chain.append(titles[parent])
            parent = _parent_number(parent)
        crumbs[section.number] = " › ".join(reversed(chain))
    return crumbs


def build_chunks(doc: TakamDocument) -> list[Chunk]:
    chunks: list[Chunk] = []
    crumbs = _breadcrumbs(doc.sections)
    for ordinal, section in enumerate(doc.sections):
        body = section.content.strip()
        if not body and not section.title:
            continue
        # כותרות האב והכותרת נכללות בטקסט הקטע — הן נושאות את מילות ההקשר
        crumb = crumbs.get(section.number, "")
        header = " › ".join(part for part in (crumb, section.title) if part)
        full = f"{header}\n{body}".strip()
        weight = 0.5 if REFERENCE_LIST_TITLE in header else 1.0
        pieces = _split_long_text(full) if len(full) > MAX_CHUNK_CHARS else [full]
        for i, piece in enumerate(pieces):
            suffix = f"-{i}" if len(pieces) > 1 else ""
            # ordinal מבטיח ייחודיות — מספרי סעיפים חוזרים בין נספחים
            chunks.append(Chunk(
                chunk_id=f"{doc.doc_id}:{ordinal}:{section.number or 'intro'}{suffix}",
                doc_id=doc.doc_id,
                instruction_number=doc.instruction_number,
                doc_title=doc.title,
                chapter=doc.chapter,
                section_number=section.number,
                section_title=section.title,
                url=doc.url,
                effective_date=doc.effective_date,
                text=piece,
                weight=weight,
            ))
    return chunks
