"""בדיקות לשכבת התפעול והאבטחה: rate limiting, כותרות, מדדים, משוב, cache."""

import importlib
import json

import pytest
from fastapi.testclient import TestClient

from takam_assistant.security import SlidingWindowRateLimiter, sanitize_question


@pytest.fixture()
def client(sample_index, tmp_path, monkeypatch):
    index_path = tmp_path / "index.json"
    sample_index.save(index_path)
    monkeypatch.setenv("TAKAM_INDEX", str(index_path))
    monkeypatch.setenv("TAKAM_FEEDBACK", str(tmp_path / "feedback.jsonl"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    from takam_assistant import api
    from takam_assistant.observability import metrics
    importlib.reload(api)
    metrics.reset()
    return TestClient(api.app)


# --- יחידות: rate limiter ו-sanitization ---

def test_rate_limiter_blocks_after_limit():
    limiter = SlidingWindowRateLimiter(limit=3, window_seconds=60)
    assert all(limiter.allow("1.2.3.4") for _ in range(3))
    assert not limiter.allow("1.2.3.4")
    assert limiter.allow("5.6.7.8")  # מפתח אחר לא נחסם


def test_sanitize_strips_control_chars():
    assert sanitize_question("שא\x00לה\x1b עם זבל\n") == "שאלה עם זבל"


# --- אינטגרציה דרך ה-API ---

def test_security_headers_present(client):
    response = client.get("/api/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "Content-Security-Policy" in response.headers
    assert response.headers["X-Request-ID"]


def test_incoming_request_id_is_respected(client):
    response = client.get("/api/health", headers={"X-Request-ID": "trace-123"})
    assert response.headers["X-Request-ID"] == "trace-123"


def test_rate_limit_via_api(client, monkeypatch):
    monkeypatch.setenv("TAKAM_RATE_LIMIT", "2")
    from takam_assistant import api
    api._rate_limiter = None  # אילוץ טעינה מחדש עם המגבלה החדשה
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/health").status_code == 429


def test_metrics_endpoint_counts_requests(client):
    client.post("/api/ask", json={"question": "מהי ערבות ביצוע?"})
    data = client.get("/api/metrics").json()
    assert data["counters"]["requests_total"] >= 1
    assert data["counters"]["mode_extractive"] == 1
    assert data["latency_ms"]["count"] >= 1


def test_feedback_is_persisted(client, tmp_path):
    response = client.post("/api/feedback", json={
        "question": "מהי ערבות ביצוע?", "mode": "extractive", "helpful": False,
        "comment": "התשובה לא כללה את שיעור הערבות",
    })
    assert response.status_code == 200
    records = [json.loads(line) for line in
               (tmp_path / "feedback.jsonl").read_text(encoding="utf-8").splitlines()]
    assert records[0]["helpful"] is False
    assert "שיעור" in records[0]["comment"]


def test_ask_rejects_control_char_only_question(client):
    response = client.post("/api/ask", json={"question": "\x01\x02"})
    assert response.status_code == 422
