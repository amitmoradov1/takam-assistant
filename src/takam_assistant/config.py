"""קונפיגורציה מרכזית — כל משתני הסביבה במקום אחד.

נקראת דינמית (ולא בזמן import) כדי שבדיקות וסביבות שונות יוכלו לשנות
הגדרות בלי טריקים. העלות זניחה והבהירות גבוהה.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    index_path: Path
    top_k: int
    model: str
    # אבטחה ותפעול
    rate_limit_per_minute: int
    log_questions: bool          # ברירת מחדל: לא לרשום תוכן שאלות ללוג (פרטיות)
    answer_cache_size: int
    feedback_path: Path


def get_settings() -> Settings:
    return Settings(
        index_path=Path(os.environ.get("TAKAM_INDEX", ROOT / "data" / "index.json")),
        top_k=int(os.environ.get("TAKAM_TOP_K", "5")),
        # Sonnet 5: איזון איכות/עלות/מהירות לשאלות-תשובות מעוגנות-מקור;
        # ניתן להחליף ב-claude-opus-5 (איכות מרבית) דרך משתנה הסביבה
        model=os.environ.get("TAKAM_MODEL", "claude-sonnet-5"),
        rate_limit_per_minute=int(os.environ.get("TAKAM_RATE_LIMIT", "30")),
        log_questions=os.environ.get("TAKAM_LOG_QUESTIONS", "0") == "1",
        answer_cache_size=int(os.environ.get("TAKAM_CACHE_SIZE", "256")),
        feedback_path=Path(os.environ.get("TAKAM_FEEDBACK", ROOT / "data" / "feedback.jsonl")),
    )
