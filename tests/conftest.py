"""Спільні фікстури тестів сервісу.

Кожен тест отримує **окреме тимчасове сховище** і режим scripted, тому детерміновані
перевірки не залежать від реальної моделі (правило 3 у specs/constitution.md).
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FAULTLOG_STORAGE", str(tmp_path / "faults.json"))
    monkeypatch.setenv("FAULTLOG_AI_MODE", "scripted")
    with TestClient(app) as test_client:
        yield test_client


def snapshot(client) -> tuple[int, list[dict]]:
    """Повний стан списку: кількість і записи з усіма полями (рішення C-9)."""
    response = client.get("/faults")
    assert response.status_code == 200
    payload = response.json()
    return payload["count"], payload["items"]
