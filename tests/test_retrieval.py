from takam_assistant.index import BM25Index


def test_retrieval_finds_relevant_instruction(sample_index: BM25Index):
    results = sample_index.search("מהי התקרה להתקשרות בפטור ממכרז?", k=3)
    assert results
    assert results[0].chunk.instruction_number == "7.2.1"


def test_retrieval_handles_hebrew_prefixes(sample_index: BM25Index):
    # "בערבות", "לערבויות" — צורות מוטות של אותו מושג
    results = sample_index.search("מתי נדרשת ערבות ביצוע ומה שיעורה?", k=3)
    assert results[0].chunk.instruction_number == "7.7.1"


def test_instruction_number_in_query_boosts_that_instruction(sample_index: BM25Index):
    results = sample_index.search("מה קובעת הוראה 7.4.3.8 לגבי עיון במסמכים?", k=3)
    assert results[0].chunk.instruction_number == "7.4.3.8"


def test_cross_chapter_query(sample_index: BM25Index):
    results = sample_index.search("החזר נסיעה ברכב פרטי קילומטראז'", k=3)
    assert results[0].chunk.instruction_number == "13.9.2"


def test_empty_index_returns_nothing():
    assert BM25Index().search("שאלה כלשהי") == []


def test_save_load_roundtrip(tmp_path, sample_index: BM25Index):
    path = tmp_path / "index.json"
    sample_index.save(path)
    loaded = BM25Index.load(path)
    original = sample_index.search("ערבות ביצוע", k=1)[0]
    reloaded = loaded.search("ערבות ביצוע", k=1)[0]
    assert reloaded.chunk.chunk_id == original.chunk.chunk_id
    assert abs(reloaded.score - original.score) < 1e-9
