"""בדיקות לסקרייפר — ללא רשת: זיהוי מקורות, בחירת גרסה, מטא-דאטה, חילוץ
HTML ומניפסט."""

from pathlib import Path

from takam_assistant.scraper import (
    CODE_LINE_RE,
    extract_html_text,
    guess_metadata,
    load_manifest,
    pick_latest_version,
    save_manifest,
)


def test_source_line_classification():
    # מספר הוראה → איסוף דרך ה-API; כל השאר → איסוף גנרי מ-URL
    assert CODE_LINE_RE.match("7.6.1")
    assert CODE_LINE_RE.match("13.9.2")
    assert not CODE_LINE_RE.match("https://takam.mof.gov.il/document/H.7.6.1")
    assert not CODE_LINE_RE.match("7")


def test_pick_latest_version_prefers_newest_published():
    versions = [
        {"rtn_status__c": "Published", "rtn_archived__c": False,
         "rtn_versionnumber__c": 11, "rtn_contentversionid__c": "old"},
        {"rtn_status__c": "Published", "rtn_archived__c": False,
         "rtn_versionnumber__c": 12, "rtn_contentversionid__c": "new"},
        {"rtn_status__c": "Published", "rtn_archived__c": True,   # ארכיון
         "rtn_versionnumber__c": 13, "rtn_contentversionid__c": "archived"},
        {"rtn_status__c": "Draft", "rtn_archived__c": False,      # טיוטה
         "rtn_versionnumber__c": 14, "rtn_contentversionid__c": "draft"},
    ]
    assert pick_latest_version(versions)["rtn_contentversionid__c"] == "new"
    assert pick_latest_version([]) is None


def test_extract_html_prefers_main_and_drops_chrome():
    html = """<html><head><title>הוראה 7.2.1</title></head><body>
      <nav>תפריט ניווט</nav><script>var x=1;</script>
      <main><h1>התקשרות בפטור ממכרז</h1><p>תוכן ההוראה.</p></main>
      <footer>כל הזכויות שמורות</footer></body></html>"""
    title, text = extract_html_text(html)
    assert title == "הוראה 7.2.1"
    assert "תוכן ההוראה" in text
    assert "תפריט ניווט" not in text and "var x" not in text


def test_guess_metadata_extracts_instruction_number():
    meta = guess_metadata("https://x.gov.il/doc", 'הוראת תכ"ם 7.4.3.8 — ניהול מכרז', "")
    assert meta["instruction_number"] == "7.4.3.8"
    meta = guess_metadata("https://x.gov.il/files/7.2.1.pdf", "", "")
    assert meta["instruction_number"] == "7.2.1"


def test_manifest_roundtrip(tmp_path: Path):
    manifest = {"https://x.gov.il/doc/7.2.1": "takam-7.2.1.json"}
    save_manifest(tmp_path, manifest)
    assert load_manifest(tmp_path) == manifest
    # המניפסט לא ייקלט בטעות כמסמך ע"י build_index (שם מתחיל ב-_)
    assert (tmp_path / "_manifest.json").exists()
