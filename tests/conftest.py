import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from takam_assistant.chunking import build_chunks  # noqa: E402
from takam_assistant.index import BM25Index  # noqa: E402
from takam_assistant.parsing import TakamDocument  # noqa: E402


@pytest.fixture(scope="session")
def sample_docs() -> list[TakamDocument]:
    docs = []
    for path in sorted((ROOT / "data" / "sample").glob("*.json")):
        docs.append(TakamDocument.from_dict(json.loads(path.read_text(encoding="utf-8"))))
    assert docs, "נתוני הדוגמה חסרים"
    return docs


@pytest.fixture(scope="session")
def sample_index(sample_docs) -> BM25Index:
    chunks = [chunk for doc in sample_docs for chunk in build_chunks(doc)]
    index = BM25Index()
    index.build(chunks)
    return index
