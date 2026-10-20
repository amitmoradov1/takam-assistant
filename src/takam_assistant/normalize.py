"""נרמול וטוקניזציה של טקסט עברי.

עברית היא שפה מוטה-תחיליות: "ההתקשרות", "בהתקשרות", "להתקשרות" הן כולן
צורות של "התקשרות". חיפוש מילות-מפתח נאיבי מפספס אותן, ולכן אנחנו:

1. מסירים ניקוד וסימני פיסוק.
2. מנרמלים אותיות סופיות (ם→מ, ן→נ, ץ→צ, ף→פ, ך→כ).
3. מייצרים לכל טוקן גם וריאנטים עם הסרת תחיליות נפוצות (ו, ה, ב, ל, מ, ש, כ
   וצירופיהן), כך שהאינדקס והשאילתה נפגשים על צורת הבסיס.

זה לא ניתוח מורפולוגי מלא (אין לנו תלות חיצונית ב-POC), אבל בפועל זה סוגר
את רוב הפער עבור טקסט מנהלי.
"""

from __future__ import annotations

import re
import unicodedata

# תחיליות נפוצות בעברית, מהארוכה לקצרה כדי שהסרה חמדנית תעבוד נכון
_PREFIXES = (
    "וכש", "לכש", "כש", "וה", "שה", "בה", "לה", "מה", "כה",
    "ו", "ה", "ב", "ל", "מ", "ש", "כ",
)

_FINALS = str.maketrans("םןץףך", "מנצפכ")

_NIKUD_RE = re.compile(r"[֑-ׇ]")
_TOKEN_RE = re.compile(r"[\w֐-׿]+(?:\.\d+)*", re.UNICODE)

# מילות עצירה מינימליות — מילים שלא נושאות משמעות לחיפוש
_STOPWORDS = {
    "של", "על", "את", "או", "גם", "כי", "אם", "לא", "יש", "אין",
    "זה", "זו", "הוא", "היא", "הם", "הן", "כל", "אשר", "בין", "עם",
    "לפי", "כפי", "וכן", "לגבי", "בו", "בה", "כאשר", "כמו",
}


def strip_nikud(text: str) -> str:
    return _NIKUD_RE.sub("", unicodedata.normalize("NFC", text))


def base_tokens(text: str) -> list[str]:
    """טוקנים גולמיים: ללא ניקוד, אותיות סופיות מנורמלות, לטינית באותיות קטנות."""
    text = strip_nikud(text).translate(_FINALS).lower()
    return [t for t in _TOKEN_RE.findall(text) if len(t) > 1 and t not in _STOPWORDS]


def _prefix_variants(token: str) -> set[str]:
    """הטוקן עצמו + צורות עם הסרת תחילית אחת (אם נותר בסיס סביר)."""
    variants = {token}
    if token[0].isdigit():  # מספרי סעיפים (7.4.3.8) נשארים כמו שהם
        return variants
    for prefix in _PREFIXES:
        if token.startswith(prefix) and len(token) - len(prefix) >= 3:
            variants.add(token[len(prefix):])
            break  # מסירים תחילית אחת בלבד — לא "מקלפים" את כל המילה
    return variants


def index_terms(text: str) -> list[str]:
    """מונחים לאינדוקס/שאילתה: כל טוקן + וריאנטים ללא תחיליות."""
    terms: list[str] = []
    for token in base_tokens(text):
        terms.extend(_prefix_variants(token))
    return terms


INSTRUCTION_NUMBER_RE = re.compile(r"\b(\d{1,2}(?:\.\d{1,2}){1,4})\b")


def extract_instruction_numbers(text: str) -> list[str]:
    """מספרי הוראה/סעיף שמופיעים בשאילתה, למשל 7.4.3.8."""
    return INSTRUCTION_NUMBER_RE.findall(text)
