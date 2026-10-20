from takam_assistant.chunking import MAX_CHUNK_CHARS, build_chunks
from takam_assistant.parsing import TakamDocument, parse_sections


def test_sections_parsed_hierarchically():
    text = "1. כללי\nפסקת פתיחה.\n3.1 עקרונות\nתוכן העקרונות.\n3.1.1 תת סעיף\nפירוט."
    sections = parse_sections(text)
    numbers = [s.number for s in sections]
    assert numbers == ["1", "3.1", "3.1.1"]
    assert sections[1].title == "עקרונות"
    assert "תוכן העקרונות" in sections[1].content


def test_unstructured_text_becomes_single_section():
    sections = parse_sections("טקסט חופשי בלי שום מספור של סעיפים.")
    assert len(sections) == 1
    assert sections[0].number == ""


def test_bare_number_without_dot_is_not_a_heading():
    # שורת תוכן שמתחילה במספר ("30 ימים") אינה כותרת סעיף
    text = "1. כללי\n30 ימים לפני המועד יש להגיש בקשה."
    sections = parse_sections(text)
    assert [s.number for s in sections] == ["1"]
    assert "30 ימים" in sections[0].content


def test_long_numbered_line_becomes_section_with_content():
    # בהוראות אמיתיות רוב הסעיפים הם משפט מלא, לא כותרת
    long_line = "2.1.1 " + "משרד יערוך התקשרות בדרך של מכרז פומבי " * 4
    sections = parse_sections(long_line.strip())
    assert sections[0].number == "2.1.1"
    assert sections[0].title == ""
    assert "מכרז פומבי" in sections[0].content


def test_appendix_sections_get_letter_prefix():
    # המספור בנספחים מתחיל מחדש — אות הנספח מבדילה את הציטוט
    text = ("1. כללי\nגוף ההוראה.\n"
            "נספח א – הגדרות\n"
            "1. ספק – מי שמספק טובין.\n"
            "נספח ג\n"
            "2.1 תהליך האישור מפורט כאן.")
    numbers = [s.number for s in parse_sections(text)]
    assert numbers == ["1", "א", "א.1", "ג", "ג.2.1"]


def test_chunks_carry_citation_metadata(sample_docs):
    doc = next(d for d in sample_docs if d.instruction_number == "7.4.3.8")
    chunks = build_chunks(doc)
    assert chunks
    citations = [c.citation for c in chunks]
    assert any("7.4.3.8" in c and "סעיף 3.5" in c for c in citations)


def test_chunks_carry_parent_breadcrumbs():
    # מילות ההקשר של סעיף-משפט נמצאות בכותרות האב — הן חייבות להיכנס לקטע
    text = ("2. הנחיות לביצוע\n"
            "2.1 עדיפות המכרז הפומבי\n"
            "2.1.1 משרד יערוך התקשרות בדרך של מכרז פומבי, אלא אם הותר אחרת "
            "בהתאם להוראות התחיקה החלה על משרדי הממשלה כולם.")
    doc = TakamDocument(
        doc_id="t", title="בדיקה", instruction_number="9.9.9",
        chapter="", url="", effective_date="", text=text,
    )
    doc.sections = parse_sections(text)
    leaf = next(c for c in build_chunks(doc) if c.section_number == "2.1.1")
    assert "עדיפות המכרז הפומבי" in leaf.text
    assert "הנחיות לביצוע" in leaf.text


def test_reference_list_sections_get_reduced_weight():
    text = ("2. הנחיות לביצוע\n"
            "2.1 תוכן מהותי של ההוראה.\n"
            "3. מסמכים ישימים\n"
            "3.1 הוראת תכ\"ם, \"כללים להקמת רשימת מציעים\", מס' 7.13.1.")
    doc = TakamDocument(
        doc_id="t", title="בדיקה", instruction_number="9.9.9",
        chapter="", url="", effective_date="", text=text,
    )
    doc.sections = parse_sections(text)
    chunks = {c.section_number: c for c in build_chunks(doc)}
    assert chunks["2.1"].weight == 1.0
    assert chunks["3.1"].weight == 0.5


def test_file_url_carried_to_chunks():
    # קישור הנוסח המחייב עובר מהמסמך לכל קטע — ממנו ל-API ול-UI
    doc = TakamDocument.from_dict({
        "doc_id": "t", "title": "בדיקה", "instruction_number": "9.9.9",
        "text": "1. כללי\nתוכן.",
        "file_url": "https://takam.mof.gov.il/api/DocumentSF/DownloadDocument/x/t.docx",
    })
    chunks = build_chunks(doc)
    assert all(c.file_url == doc.file_url for c in chunks)


def test_appendix_citation_label():
    text = "נספח ג\n2.1 תהליך האישור."
    doc = TakamDocument(
        doc_id="t", title="בדיקה", instruction_number="9.9.9",
        chapter="", url="", effective_date="", text=text,
    )
    doc.sections = parse_sections(text)
    chunk = next(c for c in build_chunks(doc) if c.section_number == "ג.2.1")
    assert "נספח ג, סעיף 2.1" in chunk.citation


def test_long_sections_split_with_size_limit():
    long_text = "1. סעיף ארוך\n" + " ".join(f"משפט מספר {i}." for i in range(400))
    doc = TakamDocument(
        doc_id="t", title="בדיקה", instruction_number="9.9.9",
        chapter="", url="", effective_date="", text=long_text,
    )
    doc.sections = parse_sections(long_text)
    chunks = build_chunks(doc)
    assert len(chunks) > 1
    assert all(len(c.text) <= MAX_CHUNK_CHARS * 1.3 for c in chunks)
    # כל חלקי הסעיף שומרים על שיוך לסעיף המקורי
    assert all(c.section_number == "1" for c in chunks)
