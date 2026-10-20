"""ניטור ולוגים.

- לוגים מובנים בפורמט JSON (שורה לאירוע) — ניתנים לשאיבה ישירה ל-ELK/Splunk/
  Grafana Loki בלי parsing מיוחד.
- request_id לכל בקשה (או כזה שהגיע מה-proxy בכותרת X-Request-ID) — מאפשר
  לקשר לוג תשובה ללוג אחזור ללוג שגיאה של אותה בקשה.
- מדדים in-memory שנחשפים ב-/api/metrics: ספירות, שיעור שגיאות, ו-latency
  (ממוצע ו-p95). ב-production מחליפים ב-Prometheus client — הממשק זהה.
- פרטיות: תוכן השאלות לא נרשם ללוג כברירת מחדל (רק hash ואורך), כי שאלות
  עובדים עלולות לחשוף מידע רגיש. ניתן להדליק עם TAKAM_LOG_QUESTIONS=1.
"""

from __future__ import annotations

import hashlib
import json
import logging
import statistics
import sys
import threading
import time
import uuid
from collections import Counter, deque


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "event": record.getMessage(),
        }
        payload.update(getattr(record, "fields", {}))
        return json.dumps(payload, ensure_ascii=False)


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("takam")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


logger = setup_logging()


def log(event: str, level: int = logging.INFO, **fields) -> None:
    logger.log(level, event, extra={"fields": fields})


def question_fingerprint(question: str) -> str:
    """מזהה יציב לשאלה ללא חשיפת תוכנה (לצורך קיבוץ שאלות חוזרות בלוגים)."""
    return hashlib.sha256(question.strip().encode("utf-8")).hexdigest()[:12]


def new_request_id(incoming: str | None = None) -> str:
    return (incoming or "").strip()[:64] or uuid.uuid4().hex[:16]


class Metrics:
    """מדדים בזיכרון: מונים + חלון latency אחרון. Thread-safe."""

    WINDOW = 1000

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: Counter = Counter()
        self._latencies_ms: deque[float] = deque(maxlen=self.WINDOW)
        self._started = time.time()

    def inc(self, name: str, amount: int = 1) -> None:
        with self._lock:
            self._counters[name] += amount

    def observe_latency(self, ms: float) -> None:
        with self._lock:
            self._latencies_ms.append(ms)

    def snapshot(self) -> dict:
        with self._lock:
            latencies = sorted(self._latencies_ms)
            return {
                "uptime_seconds": round(time.time() - self._started, 1),
                "counters": dict(self._counters),
                "latency_ms": {
                    "count": len(latencies),
                    "avg": round(statistics.fmean(latencies), 1) if latencies else None,
                    "p95": round(latencies[int(len(latencies) * 0.95) - 1], 1)
                    if len(latencies) >= 2 else (latencies[0] if latencies else None),
                },
            }

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._latencies_ms.clear()


metrics = Metrics()
