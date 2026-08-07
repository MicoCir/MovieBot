# tests/integration/test_api.py
from fastapi.testclient import TestClient

from moviebot.interface.api import app


def test_health_endpoint():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
