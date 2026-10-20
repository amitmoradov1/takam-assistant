"""בדיקת מוכנות (preflight) והרצת המערכת בפקודה אחת.

שימוש:
    python scripts/run.py               # בודק הכול, בונה אינדקס אם צריך, ומריץ
    python scripts/run.py --check-only  # רק הבדיקות, בלי להרים שרת
    python scripts/run.py --port 8080   # פורט אחר

מה נבדק, לפי סדר:
1. גרסת Python (נדרש 3.10+).
2. שהתלויות מ-requirements.txt מותקנות.
3. טעינת .env אם קיים (כך אין צורך ב-export ידני של המפתח).
4. שיש נתונים (data/raw מהאתר, או data/sample כגיבוי).
5. שהאינדקס קיים ועדכני ביחס לנתונים — נבנה אוטומטית אם לא.
6. מפתח ANTHROPIC_API_KEY — אזהרה בלבד אם חסר (מצב אחזור-בלבד).
7. שהפורט פנוי.
"""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# שם החבילה להתקנה → שם המודול לייבוא
REQUIRED_PACKAGES = {
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "anthropic": "anthropic",
    "requests": "requests",
    "beautifulsoup4": "bs4",
    "pypdf": "pypdf",
}

OK, WARN, FAIL = "✓", "⚠", "✗"


def say(mark: str, message: str) -> None:
    print(f"  {mark} {message}")


def check_python() -> bool:
    version = sys.version_info
    if version >= (3, 10):
        say(OK, f"Python {version.major}.{version.minor}")
        return True
    say(FAIL, f"Python {version.major}.{version.minor} — נדרש 3.10 ומעלה")
    return False


def check_dependencies() -> bool:
    import importlib.util

    missing = [pkg for pkg, module in REQUIRED_PACKAGES.items()
               if importlib.util.find_spec(module) is None]
    if not missing:
        say(OK, f"כל התלויות מותקנות ({len(REQUIRED_PACKAGES)})")
        return True
    say(FAIL, f"תלויות חסרות: {', '.join(missing)}")
    print(f"      התקנה: {sys.executable} -m pip install -r requirements.txt")
    return False


def parse_env_file(text: str) -> dict[str, str]:
    """פענוח קובץ .env מינימלי: שורות KEY=VALUE, התעלמות מהערות וריקות."""
    values: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip():
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_env_file() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    loaded = []
    for key, value in parse_env_file(env_path.read_text(encoding="utf-8")).items():
        if value and key not in os.environ:   # הסביבה גוברת על הקובץ
            os.environ[key] = value
            loaded.append(key)
    if loaded:
        say(OK, f".env נטען ({', '.join(loaded)})")


def check_data() -> Path | None:
    raw = [p for p in (ROOT / "data" / "raw").glob("*.json")
           if not p.name.startswith("_")]
    if raw:
        say(OK, f"נתונים: {len(raw)} הוראות אמיתיות ב-data/raw")
        return ROOT / "data" / "raw"
    sample = list((ROOT / "data" / "sample").glob("*.json"))
    if sample:
        say(WARN, f"אין data/raw — ישמשו {len(sample)} מסמכי הדוגמה (data/sample). "
                  "לאיסוף אמיתי: python -m takam_assistant.scraper data/sources.txt")
        return ROOT / "data" / "sample"
    say(FAIL, "אין נתונים כלל (לא data/raw ולא data/sample)")
    return None


def ensure_index(data_dir: Path) -> bool:
    index_path = ROOT / "data" / "index.json"
    newest_source = max(p.stat().st_mtime for p in data_dir.glob("*.json"))
    if index_path.exists() and index_path.stat().st_mtime >= newest_source:
        say(OK, "האינדקס קיים ועדכני")
        return True
    say(WARN, "האינדקס חסר או ישן מהנתונים — בונה...")
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_index.py")], cwd=ROOT)
    if result.returncode == 0:
        say(OK, "האינדקס נבנה")
        return True
    say(FAIL, "בניית האינדקס נכשלה")
    return False


def check_api_key() -> None:
    if os.environ.get("ANTHROPIC_API_KEY"):
        say(OK, "ANTHROPIC_API_KEY מוגדר — מצב מלא (תשובות מנוסחות)")
    else:
        say(WARN, "אין ANTHROPIC_API_KEY — המערכת תרוץ במצב אחזור-בלבד. "
                  "ראו .env.example")


def check_port(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        if sock.connect_ex(("127.0.0.1", port)) == 0:
            say(FAIL, f"פורט {port} תפוס — עצרו את התהליך הקיים או בחרו --port אחר")
            return False
    say(OK, f"פורט {port} פנוי")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="בדיקת מוכנות והרצת תכ\"ם-קל")
    parser.add_argument("--check-only", action="store_true",
                        help="רק בדיקות, בלי להרים את השרת")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    print("בדיקת מוכנות תכ\"ם-קל:")
    ok = check_python()
    ok = check_dependencies() and ok
    if not ok:                      # בלי Python/תלויות אין טעם להמשיך
        sys.exit(1)

    load_env_file()
    data_dir = check_data()
    ok = data_dir is not None and ok
    ok = (data_dir is not None and ensure_index(data_dir)) and ok
    check_api_key()                 # אזהרה בלבד — לא מפיל
    ok = check_port(args.port) and ok

    if not ok:
        sys.exit("\nיש בעיות לתיקון — ראו הסימונים למעלה.")

    if args.check_only:
        print(f"\nהכול מוכן. הרצה: python scripts/run.py --port {args.port}")
        return

    print(f"\nמריץ את השרת: http://127.0.0.1:{args.port}  (עצירה: Ctrl+C)\n")
    os.execv(sys.executable, [
        sys.executable, "-m", "uvicorn", "takam_assistant.api:app",
        "--app-dir", str(ROOT / "src"), "--port", str(args.port),
    ])


if __name__ == "__main__":
    main()
