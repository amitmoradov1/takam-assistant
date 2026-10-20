"""הקשחת אבטחה ברמת ה-POC.

מה מיושם כאן (ולמה), ומה במודע נשאר ל-production — ראו README חלק ג':

1. Rate limiting פר כתובת IP (חלון הזזה בזיכרון) — בולם שימוש לרעה ושורף-עלות
   על ה-LLM. ב-production: מאחורי API Gateway או Redis למספר שרתים.
2. כותרות אבטחה לדפדפן (CSP, X-Frame-Options, nosniff) — ה-UI מרנדר טקסט
   שמקורו במסמכים שנאספו מהאינטרנט, ולכן גם escaping בצד לקוח וגם CSP.
3. ניקוי קלט — תווי בקרה מוסרים; אורך נאכף ב-schema של ה-API.
4. הגנת prompt-injection — מסמך שנאסף מהאתר יכול להכיל טקסט זדוני ("התעלם
   מההנחיות..."). המיגון: תיחום קטעי המקור בתגיות, הנחיה מפורשת למודל
   להתייחס אליהם כנתונים בלבד, והצגת המקורות למשתמש לאימות. (המיגון המלא —
   סינון בצנרת האיסוף ו-evals אדברסריאליים — מתואר ב-README.)

אין כאן אימות משתמשים: בכוונה. זו החלטה מוצהרת — בסביבה ממשלתית ההזדהות
תגיע מתשתית ארגונית (SSO/הזדהות ממשלתית) ולא ממימוש עצמי ב-POC.
"""

from __future__ import annotations

import re
import threading
import time
from collections import defaultdict, deque

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    # inline script/style נדרשים לעמוד היחיד של ה-POC; ב-production עוברים ל-nonce
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; connect-src 'self'; "
        "img-src 'self' data:; frame-ancestors 'none'"
    ),
}

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_question(question: str) -> str:
    return _CONTROL_CHARS_RE.sub("", question).strip()


class SlidingWindowRateLimiter:
    """מגביל בקשות לכל מפתח (IP) בחלון זמן. בזיכרון — מתאים לתהליך יחיד."""

    def __init__(self, limit: int, window_seconds: float = 60.0) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            return True
