"""בדיקות לסקריפט המוכנות — הלוגיקה הטהורה, ללא תהליכים ורשת."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run import REQUIRED_PACKAGES, parse_env_file  # noqa: E402


def test_parse_env_file():
    text = (
        "# הערה\n"
        "ANTHROPIC_API_KEY=sk-ant-test123\n"
        "\n"
        "QUOTED='value'\n"
        "broken-line-without-equals\n"
        "EMPTY=\n"
    )
    values = parse_env_file(text)
    assert values["ANTHROPIC_API_KEY"] == "sk-ant-test123"
    assert values["QUOTED"] == "value"
    assert "broken-line-without-equals" not in values
    assert values["EMPTY"] == ""


def test_required_packages_match_requirements_txt():
    """כל חבילה שהסקריפט בודק אכן מופיעה ב-requirements.txt — שלא יבדוק
    דבר שלא מותקן אצל הבוחן, ולהפך."""
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    declared = {line.split(">=")[0].split("==")[0].strip().lower()
                for line in requirements.splitlines()
                if line.strip() and not line.startswith("#")}
    for package in REQUIRED_PACKAGES:
        assert package.lower() in declared, f"{package} חסר ב-requirements.txt"
