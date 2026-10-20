#!/bin/sh
# תכ"ם-קל — הקמה והרצה בפקודה אחת (macOS / Linux):
#   scripts/run.sh              הרצה מלאה
#   scripts/run.sh --check-only בדיקת מוכנות בלבד
# יוצר סביבה וירטואלית אם אין, מתקין תלויות, ומריץ את scripts/run.py —
# כל הלוגיקה (בדיקות מוכנות, אינדקס, שרת) נמצאת שם, חוצת-פלטפורמות.
set -e
cd "$(dirname "$0")/.."   # שורש הפרויקט

if [ ! -d .venv ]; then
    echo "יוצר סביבה וירטואלית (.venv)..."
    python3 -m venv .venv
fi
.venv/bin/pip install --quiet -r requirements.txt
exec .venv/bin/python scripts/run.py "$@"
