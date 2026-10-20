import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(sample_index, tmp_path, monkeypatch):
    index_path = tmp_path / "index.json"
    sample_index.save(index_path)
    monkeypatch.setenv("TAKAM_INDEX", str(index_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)  # מצב אחזור דטרמיניסטי

    from takam_assistant import api
    importlib.reload(api)
    return TestClient(api.app)


def test_health(client):
    data = client.get("/api/health").json()
    assert data["status"] == "ok"
    assert data["llm_enabled"] is False


def test_ask_returns_answer_with_sources(client):
    response = client.post("/api/ask", json={"question": "מתי מותר לנהל משא ומתן עם מציעים?"})
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "extractive"
    assert data["sources"]
    assert data["sources"][0]["instruction_number"] == "7.12.3"
    assert "7.12.3" in data["answer"]
    # שדות הקישור קיימים תמיד בתשובה (ריקים בנתוני הדוגמה הסינתטיים)
    assert "url" in data["sources"][0] and "file_url" in data["sources"][0]


def test_ask_validates_input(client):
    assert client.post("/api/ask", json={"question": ""}).status_code == 422
    assert client.post("/api/ask", json={}).status_code == 422


def test_ask_unknown_topic_degrades_gracefully(client):
    response = client.post("/api/ask", json={"question": "xyzzy שאלה על נושא שאינו קיים כלל"})
    assert response.status_code == 200
    # אסור להמציא תשובה — או שאין תוצאות או שמוחזרים קטעים בציון נמוך
    assert response.json()["mode"] in {"no_results", "extractive"}


def test_stats(client):
    data = client.get("/api/stats").json()
    assert data["chunks"] > 0
    assert "7.4.3.8" in data["documents"]
