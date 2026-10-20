"""שער איכות האחזור על נתוני הדוגמה הסינתטיים (gold.sample.json) —
דטרמיניסטי ולא תלוי ברשת. הסט האמיתי (gold.json, מול data/raw) רץ
ב-CI וב-scripts/eval_retrieval.py."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from eval_retrieval import evaluate  # noqa: E402


def test_gold_set_recall(sample_index):
    gold = json.loads((ROOT / "data" / "eval" / "gold.sample.json").read_text(encoding="utf-8"))
    report = evaluate(sample_index, gold["questions"], k=5)
    assert report["recall_at_5"] >= 0.9, report["misses"]
    assert report["recall_at_1"] >= 0.7, report["misses"]


def test_llm_answer_cache(sample_index, monkeypatch):
    """תשובת LLM זהה לשאלה חוזרת מגיעה מה-cache בלי קריאה שנייה לרשת."""
    import takam_assistant.llm as llm

    calls = {"n": 0}

    def fake_llm(question, results):
        calls["n"] += 1
        return {"answer": "תשובה", "sources": [], "mode": "llm"}

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(llm, "_llm_answer", fake_llm)
    llm._cache = llm.AnswerCache()  # cache נקי לבדיקה

    results = sample_index.search("מהי ערבות ביצוע?", k=3)
    first = llm.answer_question("מהי ערבות ביצוע?", results)
    second = llm.answer_question("מהי ערבות ביצוע?", results)

    assert calls["n"] == 1
    assert "cached" not in first
    assert second["cached"] is True
    assert second["answer"] == first["answer"]
