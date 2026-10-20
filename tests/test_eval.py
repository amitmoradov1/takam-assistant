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


def test_answer_mode_detects_no_answer():
    from takam_assistant.llm import answer_mode

    assert answer_mode("לא נמצאה תשובה לשאלה זו בהוראות שבמאגר.") == "llm_no_answer"
    assert answer_mode("  לא נמצא מידע רלוונטי במקורות.") == "llm_no_answer"
    assert answer_mode("No answer to this question was found in the instructions.") == "llm_no_answer"
    assert answer_mode("תקרת הסכום היא **100,000 ₪** [מקור 1].") == "llm"
    assert answer_mode("The threshold is **100,000 ILS** [מקור 1].") == "llm"


def test_no_answer_responses_are_cached(sample_index, monkeypatch):
    """גם 'אין תשובה במאגר' נשמר ב-cache — שאלה חוזרת לא עולה קריאת API."""
    import takam_assistant.llm as llm

    calls = {"n": 0}

    def fake_llm(question, results, lang="he"):
        calls["n"] += 1
        return {"answer": "לא נמצאה תשובה לשאלה זו בהוראות שבמאגר.",
                "sources": [], "mode": "llm_no_answer"}

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(llm, "_llm_answer", fake_llm)
    llm._cache = llm.AnswerCache()

    results = sample_index.search("מי היה ראש הממשלה?", k=3)
    llm.answer_question("מי היה ראש הממשלה?", results)
    second = llm.answer_question("מי היה ראש הממשלה?", results)
    assert calls["n"] == 1
    assert second["cached"] is True


def test_answer_language_follows_ui_choice(sample_index, monkeypatch):
    """בחירת שפה בממשק קובעת את שפת התשובה ומבדלת את ה-cache —
    אותה שאלה בעברית ובאנגלית הן שתי רשומות נפרדות."""
    import takam_assistant.llm as llm

    seen_langs = []

    def fake_llm(question, results, lang="he"):
        seen_langs.append(lang)
        return {"answer": f"answer-{lang}", "sources": [], "mode": "llm"}

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(llm, "_llm_answer", fake_llm)
    llm._cache = llm.AnswerCache()

    results = sample_index.search("מהי ערבות ביצוע?", k=3)
    hebrew = llm.answer_question("מהי ערבות ביצוע?", results, lang="he")
    english = llm.answer_question("מהי ערבות ביצוע?", results, lang="en")
    assert seen_langs == ["he", "en"]        # en לא הגיע מה-cache של he
    assert hebrew["answer"] != english["answer"]


def test_no_results_answer_localized():
    from takam_assistant.llm import answer_question

    assert "לא נמצאו" in answer_question("שאלה", [], lang="he")["answer"]
    assert "No relevant" in answer_question("question", [], lang="en")["answer"]


def test_llm_answer_cache(sample_index, monkeypatch):
    """תשובת LLM זהה לשאלה חוזרת מגיעה מה-cache בלי קריאה שנייה לרשת."""
    import takam_assistant.llm as llm

    calls = {"n": 0}

    def fake_llm(question, results, lang="he"):
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
