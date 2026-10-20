from takam_assistant.normalize import (
    base_tokens,
    extract_instruction_numbers,
    index_terms,
)


def test_final_letters_normalized():
    assert base_tokens("מכרזים") == base_tokens("מכרזימ")


def test_stopwords_dropped():
    assert "של" not in base_tokens("ההצעה של המציע")


def test_prefix_variants_bridge_query_and_document():
    # המסמך אומר "ההתקשרות", המשתמש שואל "התקשרות" — חייבים להיפגש
    doc_terms = set(index_terms("ההתקשרות בפטור ממכרז"))
    query_terms = set(index_terms("התקשרות פטור מכרז"))
    assert {"התקשרות", "פטור", "מכרז"} <= doc_terms
    assert {"התקשרות", "פטור", "מכרז"} <= query_terms


def test_instruction_number_detection():
    assert extract_instruction_numbers("מה קובעת הוראה 7.4.3.8 לגבי עיון?") == ["7.4.3.8"]
    assert extract_instruction_numbers("שאלה בלי מספר") == []


def test_numbers_not_prefix_stripped():
    assert "7.4.3.8" in index_terms("הוראה 7.4.3.8")
