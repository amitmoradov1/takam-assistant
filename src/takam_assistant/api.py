"""שרת ה-API וממשק המשתמש (FastAPI).

שכבת התפעול:
- כל בקשה מקבלת request_id (או מכבדת X-Request-ID מה-proxy) ונרשמת ללוג
  JSON מובנה עם latency וסטטוס.
- כותרות אבטחה על כל תשובה, ו-rate limiting פר IP על נקודות ה-API.
- /api/metrics חושף מדדי שימוש ו-latency; /api/feedback אוסף משוב משתמשים.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from . import __version__
from .config import get_settings
from .index import BM25Index
from .llm import answer_question, translate_query_to_hebrew
from .observability import log, metrics, new_request_id, question_fingerprint
from .security import SECURITY_HEADERS, SlidingWindowRateLimiter, sanitize_question

WEB_DIR = Path(__file__).resolve().parents[2] / "web"
_HEBREW_RE = re.compile(r"[א-ת]")

app = FastAPI(title="תכ\"ם-קל", version=__version__)
_index: BM25Index | None = None
_rate_limiter: SlidingWindowRateLimiter | None = None


def get_index() -> BM25Index:
    global _index
    if _index is None:
        index_path = get_settings().index_path
        if not index_path.exists():
            raise HTTPException(
                status_code=503,
                detail="האינדקס לא נבנה עדיין. הריצו: python scripts/build_index.py",
            )
        _index = BM25Index.load(index_path)
        log("index_loaded", path=str(index_path), chunks=len(_index.chunks))
    return _index


def get_rate_limiter() -> SlidingWindowRateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = SlidingWindowRateLimiter(get_settings().rate_limit_per_minute)
    return _rate_limiter


@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    request_id = new_request_id(request.headers.get("X-Request-ID"))
    request.state.request_id = request_id
    started = time.perf_counter()

    is_api = request.url.path.startswith("/api/")
    if is_api:
        client_ip = request.client.host if request.client else "unknown"
        if not get_rate_limiter().allow(client_ip):
            metrics.inc("rate_limited")
            log("rate_limited", request_id=request_id, path=request.url.path)
            response = JSONResponse(
                status_code=429,
                content={"detail": "יותר מדי בקשות — נסו שוב בעוד דקה."},
            )
            response.headers.update(SECURITY_HEADERS)
            response.headers["X-Request-ID"] = request_id
            return response

    response = await call_next(request)

    elapsed_ms = (time.perf_counter() - started) * 1000
    if is_api:
        metrics.inc("requests_total")
        if response.status_code >= 500:
            metrics.inc("requests_errors")
        metrics.observe_latency(elapsed_ms)
        log("request", request_id=request_id, path=request.url.path,
            status=response.status_code, latency_ms=round(elapsed_ms, 1))

    response.headers.update(SECURITY_HEADERS)
    response.headers["X-Request-ID"] = request_id
    return response


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1000)


class FeedbackRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1000)
    mode: str = Field(max_length=20)
    helpful: bool
    comment: str = Field(default="", max_length=2000)


@app.get("/")
def home() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/api/health")
def health() -> dict:
    llm_enabled = bool(os.environ.get("ANTHROPIC_API_KEY"))
    return {"status": "ok", "version": __version__, "llm_enabled": llm_enabled}


@app.get("/api/stats")
def stats() -> dict:
    index = get_index()
    docs = sorted({c.instruction_number or c.doc_id for c in index.chunks})
    return {"chunks": len(index.chunks), "documents": docs}


@app.get("/api/metrics")
def get_metrics() -> dict:
    return metrics.snapshot()


@app.post("/api/ask")
def ask(request: AskRequest, http_request: Request) -> dict:
    question = sanitize_question(request.question)
    if len(question) < 2:
        raise HTTPException(status_code=422, detail="השאלה קצרה מדי.")

    settings = get_settings()
    index = get_index()

    # שאלה ללא עברית לא תתאים לאינדקס הלקסיקלי העברי — מתרגמים אותה
    # לעברית לצורך האחזור בלבד (התשובה נכתבת בשפת השאלה המקורית).
    # מחפשים על שתי הגרסאות יחד כדי לא לאבד מספרי הוראות מהמקור.
    search_query = question
    if not _HEBREW_RE.search(question):
        translated = translate_query_to_hebrew(question)
        if translated:
            search_query = f"{question} {translated}"

    retrieval_started = time.perf_counter()
    results = index.search(search_query, k=settings.top_k)
    retrieval_ms = (time.perf_counter() - retrieval_started) * 1000

    log_fields = {
        "request_id": getattr(http_request.state, "request_id", ""),
        "question_fp": question_fingerprint(question),
        "question_len": len(question),
        "retrieval_ms": round(retrieval_ms, 1),
        "results": len(results),
        "top_score": round(results[0].score, 2) if results else 0,
    }
    if settings.log_questions:  # ברירת מחדל: לא לרשום תוכן (פרטיות)
        log_fields["question"] = question
    log("ask", **log_fields)

    response = answer_question(question, results)
    response["question"] = question
    # הוראות קשורות — מגרף ההפניות הצולבות של ההוראות שהתשובה נשענת עליהן
    source_instructions = list(dict.fromkeys(
        r.chunk.instruction_number for r in results if r.chunk.instruction_number))
    response["related"] = index.related_instructions(source_instructions[:3])
    metrics.inc(f"mode_{response['mode']}")
    return response


@app.post("/api/feedback")
def feedback(request: FeedbackRequest) -> dict:
    """משוב משתמשים — נאסף ל-JSONL ומשמש בקרת איכות ובניית סט evals."""
    settings = get_settings()
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "question": request.question,
        "mode": request.mode,
        "helpful": request.helpful,
        "comment": request.comment,
    }
    settings.feedback_path.parent.mkdir(parents=True, exist_ok=True)
    with settings.feedback_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    metrics.inc("feedback_helpful" if request.helpful else "feedback_unhelpful")
    return {"status": "ok"}
