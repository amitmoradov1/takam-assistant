"""הערכת איכות האחזור מול סט שאלות זהב.

שימוש: python scripts/eval_retrieval.py [--gold data/eval/gold.json] [--k 5]

מדדים:
- recall@1 — באיזה אחוז מהשאלות ההוראה הנכונה היא התוצאה הראשונה.
- recall@k — באיזה אחוז מהשאלות ההוראה הנכונה נמצאת בין k הקטעים שנשלחים
  למודל (זה המדד הקריטי: אם המקור לא שם, שום prompt לא יציל את התשובה).
- MRR — ממוצע 1/מיקום של הפגיעה הראשונה.

זהו הבסיס לשיפור שיטתי: כל שינוי בנרמול/חלוקה/אחזור נמדד כאן לפני שנכנס.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from takam_assistant.index import BM25Index  # noqa: E402


def evaluate(index: BM25Index, gold: list[dict], k: int = 5) -> dict:
    hits_at_1 = hits_at_k = 0
    reciprocal_ranks: list[float] = []
    misses: list[dict] = []

    for item in gold:
        results = index.search(item["question"], k=k)
        ranked = [r.chunk.instruction_number for r in results]
        expected = item["expected_instruction"]

        if ranked and ranked[0] == expected:
            hits_at_1 += 1
        if expected in ranked:
            hits_at_k += 1
            reciprocal_ranks.append(1.0 / (ranked.index(expected) + 1))
        else:
            reciprocal_ranks.append(0.0)
            misses.append({"question": item["question"], "expected": expected,
                           "got": ranked[:3]})

    n = len(gold)
    return {
        "questions": n,
        "recall_at_1": round(hits_at_1 / n, 3),
        f"recall_at_{k}": round(hits_at_k / n, 3),
        "mrr": round(sum(reciprocal_ranks) / n, 3),
        "misses": misses,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", type=Path, default=ROOT / "data" / "eval" / "gold.json")
    parser.add_argument("--index", type=Path, default=ROOT / "data" / "index.json")
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args()

    if not args.index.exists():
        sys.exit("האינדקס לא נבנה. הריצו קודם: python scripts/build_index.py")

    gold = json.loads(args.gold.read_text(encoding="utf-8"))["questions"]
    report = evaluate(BM25Index.load(args.index), gold, k=args.k)

    print(f"שאלות: {report['questions']}")
    print(f"recall@1: {report['recall_at_1']:.1%}")
    print(f"recall@{args.k}: {report[f'recall_at_{args.k}']:.1%}")
    print(f"MRR: {report['mrr']:.3f}")
    if report["misses"]:
        print("\nפספוסים:")
        for miss in report["misses"]:
            print(f"  שאלה: {miss['question']}")
            print(f"    ציפינו: {miss['expected']} | קיבלנו: {miss['got']}")
    else:
        print("\nאין פספוסים בסט הנוכחי.")


if __name__ == "__main__":
    main()
