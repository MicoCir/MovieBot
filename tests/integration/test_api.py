# tests/integration/test_api.py
from fastapi.testclient import TestClient


def test_health_endpoint_without_credentials_or_dotenv(monkeypatch, tmp_path):
    for variable in (
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "OPENAI_BASE_URL",
        "TMDB_API_KEY",
        "MEILISEARCH_API_KEY",
    ):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.chdir(tmp_path)

    from moviebot.interface.api import app

    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
