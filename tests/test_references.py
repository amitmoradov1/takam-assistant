"""הפניות צולבות: חילוץ מדויק, גרף דו-כיווני, וחשיפה ב-API."""

import importlib

import pytest
from fastapi.testclient import TestClient

from takam_assistant.references import extract_references


# --- חילוץ ---

def test_extracts_reference_with_takam_prefix():
    assert extract_references('יחולו הוראות תכ"ם 7.12.3.') == ["7.12.3"]


def test_extracts_reference_with_hebrew_letter_prefix():
    assert extract_references("כמפורט בהוראה 7.4.3.8 ולהוראת 7.7.1") == ["7.4.3.8", "7.7.1"]


def test_extracts_titled_reference_style():
    # התחביר הקנוני במסמכים האמיתיים: הוראת תכ"ם, "שם", מס' X
    text = 'תיעשה בהתאם להוראת תכ"ם, "התקשרות בהליך מקוצר", מס\' 7.7.1.'
    assert extract_references(text) == ["7.7.1"]


def test_titled_reference_with_quote_variants_and_stray_dot():
    # וריאציות גרשיים ונקודה תועה לפני המספר, כפי שמופיעות בנתונים שנאספו
    text = "בהתאם להוראת תכ''ם, ''מסמכי מכרז'', מס' .7.3.1"
    assert extract_references(text) == ["7.3.1"]


def test_internal_section_numbers_are_not_references():
    # מספור סעיפים פנימי (בלי מילת ההקשר "הוראה") לא נחשב הפניה
    text = "3.1 עקרונות\n3.1.1 כאמור בסעיף 2.2 לעיל, הוועדה תדון בהצעה."
    assert extract_references(text) == []


def test_self_reference_excluded():
    assert extract_references('הוראת תכ"ם 7.2.1 קובעת...', own_number="7.2.1") == []


def test_duplicates_deduped_in_order():
    text = "בהתאם להוראה 7.7.1, וכן להוראה 7.12.3, וראו שוב הוראה 7.7.1."
    assert extract_references(text) == ["7.7.1", "7.12.3"]


# --- גרף באינדקס ---

def test_index_builds_reference_graph(sample_index):
    assert "7.12.3" in sample_index.doc_refs["7.4.3.8"]
    assert "7.7.1" in sample_index.doc_refs["7.4.3.8"]
    assert "7.4.3.8" in sample_index.doc_refs["7.12.3"]


def test_related_instructions_both_directions(sample_index):
    related = sample_index.related_instructions(["7.4.3.8"])
    by_number = {r["instruction_number"]: r for r in related}
    # יוצאות: 7.4.3.8 מפנה ל-7.12.3 ול-7.7.1
    assert by_number["7.12.3"]["relation"] == "ההוראה מפנה אליה"
    assert by_number["7.7.1"]["relation"] == "ההוראה מפנה אליה"
    # נכנסות: 7.2.1 מפנה אל 7.4.3.8
    assert by_number["7.2.1"]["relation"] == "מפנה אל ההוראה"
    # לא מחזירים את ההוראה עצמה
    assert "7.4.3.8" not in by_number


def test_related_excludes_instructions_missing_from_corpus(sample_index):
    # הפניה להוראה שלא נאספה לא תוצג (אין לאן לקשר) — נוודא שאין קריסה
    sample_index.doc_refs.setdefault("7.7.1", set()).add("99.9.9")
    related = sample_index.related_instructions(["7.7.1"])
    assert all(r["instruction_number"] != "99.9.9" for r in related)


# --- API ---

@pytest.fixture()
def client(sample_index, tmp_path, monkeypatch):
    index_path = tmp_path / "index.json"
    sample_index.save(index_path)
    monkeypatch.setenv("TAKAM_INDEX", str(index_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from takam_assistant import api
    importlib.reload(api)
    return TestClient(api.app)


def test_ask_response_includes_related(client):
    response = client.post("/api/ask", json={"question": "מי פותח את תיבת המכרזים?"})
    data = response.json()
    assert data["sources"][0]["instruction_number"] == "7.4.3.8"
    related_numbers = {r["instruction_number"] for r in data["related"]}
    assert "7.12.3" in related_numbers
    # להוראות הקשורות יש כותרת ותווית כיוון להצגה ב-UI
    assert all(r["title"] and r["relation"] for r in data["related"])