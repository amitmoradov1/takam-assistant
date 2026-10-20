# הרצה בקונטיינר — בסיס לפריסה אחידה בכל סביבה (כולל סביבה ממשלתית סגורה,
# שבה בונים את האימג' ברשת מאושרת ומעבירים אותו פנימה).
FROM python:3.13-slim

# אבטחה: ריצה כמשתמש לא-מורשה, ללא כלים מיותרים באימג'
RUN useradd --create-home appuser
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY web/ web/
COPY scripts/ scripts/
COPY data/raw/ data/raw/
COPY data/sample/ data/sample/
COPY data/eval/ data/eval/

# האינדקס נבנה בזמן build מהמדגם האמיתי (data/raw); אם אינו קיים —
# build_index.py נופל אוטומטית לנתוני הדוגמה
RUN python scripts/build_index.py && chown -R appuser:appuser /app/data

USER appuser
EXPOSE 8000

# הערה: ANTHROPIC_API_KEY מוזרק בזמן ריצה (secret) — לעולם לא נאפה לאימג'
CMD ["uvicorn", "takam_assistant.api:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000"]
