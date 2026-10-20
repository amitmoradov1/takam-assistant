"""בדיקות לחילוץ DOCX עם שחזור מספור — על קובץ DOCX מינימלי שנבנה בזיכרון,
באותו מבנה שבו משתמשים מסמכי התכ"ם האמיתיים (מספור אוטומטי דרך numPr)."""

import zipfile
from io import BytesIO

from takam_assistant.docx_extract import extract_docx_text

W_NS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'

NUMBERING_XML = f"""<?xml version="1.0" encoding="UTF-8"?>
<w:numbering {W_NS}>
  <w:abstractNum w:abstractNumId="0">
    <w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="%1."/></w:lvl>
    <w:lvl w:ilvl="1"><w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="%1.%2."/></w:lvl>
    <w:lvl w:ilvl="2"><w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="%1.%2.%3."/></w:lvl>
  </w:abstractNum>
  <w:abstractNum w:abstractNumId="1">
    <w:lvl w:ilvl="0"><w:numFmt w:val="bullet"/><w:lvlText w:val="•"/></w:lvl>
  </w:abstractNum>
  <w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>
  <w:num w:numId="2"><w:abstractNumId w:val="1"/></w:num>
</w:numbering>"""

STYLES_XML = f"""<?xml version="1.0" encoding="UTF-8"?>
<w:styles {W_NS}>
  <w:style w:styleId="Heading1"><w:pPr><w:numPr><w:numId w:val="1"/></w:numPr></w:pPr></w:style>
</w:styles>"""


def _p(text: str, num_id: str | None = None, ilvl: int = 0,
       style: str | None = None) -> str:
    props = ""
    if style:
        props += f'<w:pStyle w:val="{style}"/>'
    if num_id:
        props += f'<w:numPr><w:ilvl w:val="{ilvl}"/><w:numId w:val="{num_id}"/></w:numPr>'
    return f"<w:p><w:pPr>{props}</w:pPr><w:r><w:t>{text}</w:t></w:r></w:p>"


def make_docx(paragraphs: list[str]) -> bytes:
    document = (f'<?xml version="1.0" encoding="UTF-8"?><w:document {W_NS}>'
                f"<w:body>{''.join(paragraphs)}</w:body></w:document>")
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", document)
        archive.writestr("word/numbering.xml", NUMBERING_XML)
        archive.writestr("word/styles.xml", STYLES_XML)
    return buffer.getvalue()


def test_hierarchical_numbering_is_reconstructed():
    docx = make_docx([
        _p("מבוא", "1", 0),
        _p("פסקה ראשונה", "1", 1),
        _p("פסקה שנייה", "1", 1),
        _p("תת סעיף", "1", 2),
        _p("הנחיות לביצוע", "1", 0),   # קידום רמה 0 מאפס את העמוקות
        _p("הנחיה", "1", 1),
    ])
    lines = extract_docx_text(docx).splitlines()
    assert lines == [
        "1. מבוא",
        "1.1. פסקה ראשונה",
        "1.2. פסקה שנייה",
        "1.2.1. תת סעיף",
        "2. הנחיות לביצוע",
        "2.1. הנחיה",
    ]


def test_bullets_and_plain_paragraphs_get_no_number():
    docx = make_docx([
        _p("כותרת", "1", 0),
        _p("טקסט רגיל ללא מספור"),
        _p("פריט ברשימת תבליטים", "2", 0),
    ])
    lines = extract_docx_text(docx).splitlines()
    assert lines == ["1. כותרת", "טקסט רגיל ללא מספור", "פריט ברשימת תבליטים"]


def test_style_based_numbering_resolved_from_styles_xml():
    docx = make_docx([_p("כותרת מסוגננת", style="Heading1")])
    assert extract_docx_text(docx) == "1. כותרת מסוגננת"


def test_broken_ref_field_garbage_is_cleaned():
    garbage = ("ראה סעיף D0C9EA79F9BACE118C8200AA004BA90B0200000008"
               "Error! Reference source not found. להלן")
    docx = make_docx([_p(garbage)])
    text = extract_docx_text(docx)
    assert "D0C9EA79" not in text
    assert "Error!" not in text
    assert "ראה סעיף" in text and "להלן" in text
