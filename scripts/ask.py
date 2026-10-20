"""שאילת שאלה מהטרמינל, בלי להרים שרת.

שימוש: python scripts/ask.py "מהם תנאי הסף להשתתפות במכרז?"
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from takam_assistant.index import BM25Index  # noqa: E402
from takam_assistant.llm import answer_question  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit('שימוש: python scripts/ask.py "השאלה שלך"')
    question = " ".join(sys.argv[1:])

    index_path = ROOT / "data" / "index.json"
    if not index_path.exists():
        sys.exit("האינדקס לא נבנה. הריצו קודם: python scripts/build_index.py")

    index = BM25Index.load(index_path)
    result = answer_question(question, index.search(question, k=5))

    print(f"\n{result['answer']}\n")
    if result["sources"]:
        print("מקורות:")
        for source in result["sources"]:
            print(f"  [{source['n']}] {source['citation']}")


if __name__ == "__main__":
    main()
