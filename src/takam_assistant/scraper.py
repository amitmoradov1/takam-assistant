"""איסוף הוראות מאתר הוראות התכ"ם (takam.mof.gov.il).

שימוש (מדגם ממוקד, כמומלץ במטלה):
       python -m takam_assistant.scraper data/sources.txt

קובץ המקורות מכיל שורה לכל מקור, באחת משתי צורות:
- מספר הוראה, למשל "7.6.1" — נאסף דרך ה-API של האתר (הדרך המומלצת).
- כתובת URL מלאה לעמוד HTML או לקובץ PDF — לאיסוף גנרי ממקור אחר.

איך עובד האיסוף דרך ה-API:
אתר התכ"ם הוא אפליקציית Angular; עמודי ההוראות מרונדרים ב-JavaScript ולכן
scraping של ה-HTML מחזיר עמוד ריק. במקום להילחם בזה עם דפדפן-ללא-ראש,
מיפינו (דרך קריאות הרשת של האתר) את ה-API הפנימי שמזין אותו:

1. GET /api/Document/DocumentCodeText/H.{code} — מטא-דאטה של ההוראה
   (שם, פרק, תאריך תחולה, sfid).
2. GET /api/DocumentVersion/{sfid} — רשימת גרסאות; נבחרת הגרסה המפורסמת
   (Published, לא ארכיון) עם מספר הגרסה הגבוה ביותר.
3. GET /api/DocumentSF/DownloadDocument/{contentId}/{name} — קובץ ה-DOCX
   של ההוראה; הטקסט מחולץ עם שחזור מספור הסעיפים (ראו docx_extract.py).

זה גם יתרון ל-production: מקור מובנה ויציב יותר מ-HTML, עם זיהוי גרסאות
מובנה (versionnumber) לעדכון אינקרמנטלי של האינדקס.

תכונות:
- איסוף אינקרמנטלי: מניפסט (_manifest.json) זוכר מה כבר נאסף, כך שהרצה
  חוזרת מורידה רק חדשות (--force אוסף הכל מחדש).
- עמידות: עד 3 ניסיונות לכל מקור עם השהיה גדלה; כשל בודד לא עוצר את השאר.
- נימוס: השהיה בין בקשות ו-User-Agent מזוהה.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from io import BytesIO
from pathlib import Path
import requests
from bs4 import BeautifulSoup

from .docx_extract import extract_docx_text

USER_AGENT = "takam-assistant-poc/0.1 (home assignment; contact: candidate)"
TAKAM_BASE = "https://takam.mof.gov.il"
DELAY_SECONDS = 1.5
RETRIES = 3
TIMEOUT = 60

INSTRUCTION_RE = re.compile(r"(\d{1,2}(?:\.\d{1,2}){1,4})")
# שורת מקור שהיא מספר הוראה (ולא URL)
CODE_LINE_RE = re.compile(r"^\d{1,2}(?:\.\d{1,2}){1,3}$")


# --- הורדה ---

def fetch(url: str) -> requests.Response:
    last_error: Exception | None = None
    for attempt in range(RETRIES):
        try:
            response = requests.get(url, headers={"User-Agent": USER_AGENT},
                                    timeout=TIMEOUT)
            response.raise_for_status()
            return response
        except requests.RequestException as error:
            last_error = error
            time.sleep(2 * (attempt + 1))
    raise last_error  # type: ignore[misc]


# --- איסוף דרך ה-API של אתר התכ"ם ---

def pick_latest_version(versions: list[dict]) -> dict | None:
    """הגרסה המפורסמת העדכנית ביותר (Published, לא בארכיון)."""
    published = [v for v in versions
                 if v.get("rtn_status__c") == "Published"
                 and not v.get("rtn_archived__c")
                 and v.get("rtn_contentversionid__c")]
    if not published:
        return None
    return max(published, key=lambda v: v.get("rtn_versionnumber__c") or 0)


def scrape_takam_instruction(code: str) -> dict:
    """אוסף הוראה לפי מספרה (למשל "7.6.1") דרך ה-API של האתר."""
    meta_url = f"{TAKAM_BASE}/api/Document/DocumentCodeText/H.{code}"
    records = fetch(meta_url).json()
    if not records:
        raise ValueError(f"הוראה {code} לא נמצאה באתר (H.{code})")
    meta = records[0]

    versions = fetch(f"{TAKAM_BASE}/api/DocumentVersion/{meta['sfid']}").json()
    version = pick_latest_version(versions)
    if version is None:
        raise ValueError(f"להוראה {code} אין גרסה מפורסמת להורדה")

    content_id = version["rtn_contentversionid__c"]
    download_url = f"{TAKAM_BASE}/api/DocumentSF/DownloadDocument/{content_id}/takam-{code}.docx"
    text = extract_docx_text(fetch(download_url).content)

    effective_date = (version.get("rtn_validfrom__c")
                      or meta.get("datevalidfrom") or "")[:10]
    return {
        "doc_id": f"takam-{code}",
        "title": meta.get("name", ""),
        "instruction_number": code,
        "chapter": meta.get("firstnamechapter", ""),
        "sub_chapter": meta.get("secondnamechapter", ""),
        "url": f"{TAKAM_BASE}/document/{meta.get('documentcodetext', f'H.{code}')}",
        "effective_date": effective_date,
        "version": version.get("rtn_versionnumber__c"),
        "text": text,
    }


# --- איסוף גנרי מ-URL (עמוד HTML או קובץ PDF) ---

def extract_html_text(html: str) -> tuple[str, str]:
    """(title, text) מתוך עמוד הוראה. selectors גנריים עם fallback לכל העמוד."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()

    title = soup.title.get_text(strip=True) if soup.title else ""
    main = soup.find("main") or soup.find("article") or soup.body or soup
    lines = [line.strip() for line in main.get_text("\n").splitlines()]
    text = "\n".join(line for line in lines if line)
    return title, text


def extract_pdf_text(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(BytesIO(data))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def guess_metadata(url: str, title: str, text: str) -> dict:
    sample = f"{title} {url} {text[:500]}"
    match = INSTRUCTION_RE.search(sample)
    return {
        "instruction_number": match.group(1) if match else "",
        "title": title or url.rsplit("/", 1)[-1],
    }


def scrape_url(url: str, index_hint: int) -> dict:
    response = fetch(url)
    content_type = response.headers.get("content-type", "")
    if url.lower().endswith(".docx") or "wordprocessingml" in content_type:
        text = extract_docx_text(response.content)
        title = url.rsplit("/", 1)[-1].removesuffix(".docx")
    elif url.lower().endswith(".pdf") or "pdf" in content_type:
        text = extract_pdf_text(response.content)
        title = url.rsplit("/", 1)[-1].removesuffix(".pdf")
    else:
        title, text = extract_html_text(response.text)

    meta = guess_metadata(url, title, text)
    return {
        "doc_id": f"takam-{meta['instruction_number'] or index_hint}",
        "title": meta["title"],
        "instruction_number": meta["instruction_number"],
        "chapter": "",
        "url": url,
        "effective_date": "",
        "text": text,
    }


# --- מניפסט לאיסוף אינקרמנטלי ---

def _manifest_path(out_dir: Path) -> Path:
    return out_dir / "_manifest.json"


def load_manifest(out_dir: Path) -> dict:
    path = _manifest_path(out_dir)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def save_manifest(out_dir: Path, manifest: dict) -> None:
    _manifest_path(out_dir).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


# --- איסוף ---

def scrape_one(source: str, index_hint: int) -> dict:
    if CODE_LINE_RE.match(source):
        return scrape_takam_instruction(source)
    return scrape_url(source, index_hint)


def scrape(sources: list[str], out_dir: Path, force: bool = False) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {} if force else load_manifest(out_dir)

    pending = [s for s in sources if s not in manifest]
    skipped = len(sources) - len(pending)
    if skipped:
        print(f"מדלג על {skipped} מקורות שכבר נאספו (--force לאיסוף מחדש).")
    print(f"אוסף {len(pending)} מקורות...")

    succeeded = failed = 0
    for i, source in enumerate(pending):
        try:
            doc = scrape_one(source, index_hint=len(manifest) + i)
            out_path = out_dir / f"{doc['doc_id']}.json"
            out_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2),
                                encoding="utf-8")
            manifest[source] = out_path.name
            succeeded += 1
            print(f"  [{i + 1}/{len(pending)}] נשמר: {out_path.name} "
                  f"({len(doc['text'])} תווים, {doc['title'][:40]})")
        except Exception as error:
            failed += 1
            print(f"  [{i + 1}/{len(pending)}] שגיאה באיסוף {source}: {error}",
                  file=sys.stderr)
        save_manifest(out_dir, manifest)  # שמירה שוטפת — עמידות להפסקות
        time.sleep(DELAY_SECONDS)

    print(f"\nסיכום: {succeeded} נאספו, {failed} נכשלו, {skipped} דולגו.")
    if succeeded:
        print("השלב הבא: python scripts/build_index.py")


def main() -> None:
    parser = argparse.ArgumentParser(description="איסוף הוראות תכ\"ם")
    parser.add_argument("sources_file", type=Path,
                        help="קובץ עם מספר הוראה או URL בכל שורה (ראו data/sources.txt)")
    parser.add_argument("out_dir", nargs="?", type=Path, default=Path("data/raw"),
                        help="תיקיית פלט (ברירת מחדל: data/raw)")
    parser.add_argument("--force", action="store_true",
                        help="איסוף מחדש גם של מקורות שכבר נאספו")
    args = parser.parse_args()

    sources = [s.strip() for s in args.sources_file.read_text(encoding="utf-8").splitlines()
               if s.strip() and not s.strip().startswith("#")]
    sources = list(dict.fromkeys(sources))  # ייחודיות תוך שמירת סדר
    if not sources:
        parser.error(f"לא נמצאו מקורות ב-{args.sources_file}")

    scrape(sources, args.out_dir, force=args.force)


if __name__ == "__main__":
    main()
