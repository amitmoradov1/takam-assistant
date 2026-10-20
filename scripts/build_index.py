"""בניית אינדקס האחזור מתוך מסמכי המקור.

שימוש: python scripts/build_index.py [--source data/raw]
ברירת מחדל: data/raw אם יש בו מסמכים, אחרת data/sample (נתוני הדוגמה).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from takam_assistant.chunking import build_chunks  # noqa: E402
from takam_assistant.index import BM25Index  # noqa: E402
from takam_assistant.parsing import TakamDocument  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "index.json")
    args = parser.parse_args()

    source = args.source
    if source is None:
        raw = ROOT / "data" / "raw"
        sample = ROOT / "data" / "sample"
        source = raw if any(raw.glob("*.json")) else sample
        if source == sample:
            print("אין מסמכים ב-data/raw — משתמש בנתוני הדוגמה (data/sample).")
            print("לאיסוף מסמכים אמיתיים: python -m takam_assistant.scraper data/urls.txt data/raw")

    # קבצים שמתחילים ב-_ (כמו _manifest.json של הסקרייפר) אינם מסמכים
    docs = [TakamDocument.from_dict(json.loads(p.read_text(encoding="utf-8")))
            for p in sorted(source.glob("*.json")) if not p.name.startswith("_")]
    if not docs:
        sys.exit(f"לא נמצאו מסמכים ב-{source}")

    chunks = [chunk for doc in docs for chunk in build_chunks(doc)]
    index = BM25Index()
    index.build(chunks)
    index.save(args.out)
    print(f"נבנה אינדקס: {len(docs)} מסמכים, {len(chunks)} קטעים → {args.out}")


if __name__ == "__main__":
    main()
