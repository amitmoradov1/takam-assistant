"""אינדקס אחזור BM25 מותאם-עברית, ללא תלויות חיצוניות.

בחרנו BM25 (ולא embeddings) לשכבת האחזור של ה-POC בכוונה:
- אפס תלות בשירות חיצוני — עובד גם ברשת ממשלתית סגורה (ראו README, חלק ג').
- דטרמיניסטי וניתן לבדיקה ביחידות.
- בשילוב נרמול עברי (הסרת תחיליות) נותן אחזור טוב על טקסט מנהלי.
שדרוג ל-hybrid (BM25 + embeddings) מתואר ב-README כצעד production.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .chunking import Chunk
from .normalize import extract_instruction_numbers, index_terms
from .references import extract_references

K1 = 1.5
B = 0.75
# רצפת אורך אפקטיבי לנרמול: בלי זה, סעיף-הפניה זעיר ("יחולו הוראות תכ"ם
# X") שמכיל במקרה את מילות השאילתה מקבל ציון מנופח וגונב את המקום הראשון
# מהסעיף המהותי. פתולוגיה מוכרת של BM25 על קטעים קצרים מאוד.
# הערך נבחר בסריקת פרמטרים מול סט הזהב (ראו scripts/eval_retrieval.py).
MIN_EFFECTIVE_LEN = 35
# בונוס ניקוד כשהשאילתה נוקבת במספר הוראה/סעיף שתואם את הקטע
NUMBER_MATCH_BOOST = 8.0


@dataclass
class SearchResult:
    chunk: Chunk
    score: float


class BM25Index:
    def __init__(self) -> None:
        self.chunks: list[Chunk] = []
        self._term_freqs: list[Counter] = []
        self._doc_freq: Counter = Counter()
        self._doc_len: list[int] = []
        self._avg_len: float = 0.0
        # גרף הפניות בין הוראות: מספר הוראה → ההוראות שהיא מפנה אליהן
        self.doc_refs: dict[str, set[str]] = {}
        self._doc_info: dict[str, dict] = {}  # מספר הוראה → {title, url}

    def build(self, chunks: list[Chunk]) -> None:
        self.chunks = chunks
        self._term_freqs = []
        self._doc_freq = Counter()
        self._doc_len = []
        self.doc_refs = {}
        self._doc_info = {}
        for chunk in chunks:
            # כותרת ההוראה מאונדקסת עם כל קטע: שאלות רבות מנוסחות במילות
            # הכותרת ("בעל מקצוע מומחה", "פנייה מוקדמת לקבלת מידע") גם כשהן
            # לא מופיעות בגוף הסעיף
            terms = index_terms(
                f"{chunk.text} {chunk.instruction_number} {chunk.doc_title}")
            freqs = Counter(terms)
            self._term_freqs.append(freqs)
            self._doc_len.append(len(terms))
            self._doc_freq.update(freqs.keys())
            if chunk.instruction_number:
                refs = self.doc_refs.setdefault(chunk.instruction_number, set())
                refs.update(extract_references(chunk.text, chunk.instruction_number))
                self._doc_info.setdefault(chunk.instruction_number,
                                          {"title": chunk.doc_title, "url": chunk.url})
        self._avg_len = (sum(self._doc_len) / len(self._doc_len)) if chunks else 0.0

    def search(self, query: str, k: int = 5) -> list[SearchResult]:
        if not self.chunks:
            return []
        query_terms = set(index_terms(query))
        wanted_numbers = extract_instruction_numbers(query)
        n = len(self.chunks)

        results: list[SearchResult] = []
        for i, chunk in enumerate(self.chunks):
            freqs = self._term_freqs[i]
            score = 0.0
            for term in query_terms:
                tf = freqs.get(term, 0)
                if not tf:
                    continue
                df = self._doc_freq[term]
                idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
                effective_len = max(self._doc_len[i], MIN_EFFECTIVE_LEN)
                denom = tf + K1 * (1 - B + B * effective_len / (self._avg_len or 1))
                score += idf * (tf * (K1 + 1)) / denom
            score *= chunk.weight  # קטעי רשימות-הפניה מקבלים משקל מופחת

            # שאילתה שמזכירה "7.6.1" צריכה להעדיף את ההוראה הזו גם אם
            # ניסוח השאלה שונה מניסוח ההוראה. ההשוואה על גבול רכיב
            # ("7.6" תואם את 7.6.1 אך לא את 7.60.1) — startswith גולמי
            # היה גורם ל"7.1" להקפיץ גם את 7.12.3.
            for number in wanted_numbers:
                instruction = chunk.instruction_number
                if instruction == number or instruction.startswith(number + "."):
                    score += NUMBER_MATCH_BOOST
                elif chunk.section_number and (
                    chunk.section_number == number
                    or number.startswith(chunk.section_number + ".")
                ):
                    score += NUMBER_MATCH_BOOST / 2

            if score > 0:
                results.append(SearchResult(chunk=chunk, score=score))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:k]

    # --- גרף הפניות ---

    def related_instructions(self, instruction_numbers: list[str],
                             limit: int = 6) -> list[dict]:
        """הוראות קשורות להוראות נתונות, משני הכיוונים:
        יוצאות (ההוראה מפנה אליהן) ונכנסות (הן מפנות אליה).
        מוחזרות רק הוראות שקיימות במאגר (כדי שיהיה לאן לקשר)."""
        base = set(instruction_numbers)
        related: list[dict] = []
        seen: set[str] = set()

        def add(number: str, relation: str) -> None:
            if number in base or number in seen or number not in self._doc_info:
                return
            seen.add(number)
            info = self._doc_info[number]
            related.append({"instruction_number": number, "title": info["title"],
                            "url": info["url"], "relation": relation})

        for number in instruction_numbers:
            for ref in sorted(self.doc_refs.get(number, ())):
                add(ref, "ההוראה מפנה אליה")
        for number in instruction_numbers:
            for other, refs in sorted(self.doc_refs.items()):
                if number in refs:
                    add(other, "מפנה אל ההוראה")
        return related[:limit]

    # --- persistence ---

    def save(self, path: str | Path) -> None:
        payload = {"chunks": [c.to_dict() for c in self.chunks]}
        Path(path).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "BM25Index":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        index = cls()
        index.build([Chunk(**c) for c in payload["chunks"]])
        return index
