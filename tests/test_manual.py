"""AC-1: список, ручне створення, хибний ручний вхід."""

import pytest

from tests.conftest import snapshot


def test_health_reports_ai_mode(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "ai_mode": "scripted"}


def test_empty_list_contract(client):
    response = client.get("/faults")
    assert response.status_code == 200
    assert response.json() == {"count": 0, "items": []}


def test_manual_create_appears_in_list(client):
    count_before, items_before = snapshot(client)

    response = client.post(
        "/faults",
        json={"title": "Стартер не крутить", "system": "starter", "mileage_km": 120000},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "created"
    record = body["record"]
    assert record["source"] == "manual"
    assert record["safety_stop"] is False

    count_after, items_after = snapshot(client)
    assert count_after == count_before + 1

    stored = [item for item in items_after if item["id"] == record["id"]]
    assert len(stored) == 1, "запис має бути знайдений у списку за id"
    assert stored[0] == record, "поля у списку мають збігатися з полями відповіді"
    # Попередні записи не змінилися.
    assert [item for item in items_after if item["id"] != record["id"]] == items_before


def test_manual_create_allows_null_mileage(client):
    response = client.post("/faults", json={"title": "Не реагує на ключ", "system": "immobilizer"})
    assert response.status_code == 201
    assert response.json()["record"]["mileage_km"] is None


@pytest.mark.parametrize(
    "payload, expected_reason",
    [
        ({"system": "starter"}, "missing_field:title"),
        ({"title": "ок", "system": "starter"}, "title_length_or_type"),
        ({"title": "я" * 81, "system": "starter"}, "title_length_or_type"),
        ({"title": "Не заводиться", "system": "engine_block"}, "system_not_allowed:engine_block"),
        ({"title": "Не заводиться", "system": "starter", "mileage_km": -5}, "mileage_type_or_range"),
        ({"title": "Не заводиться", "system": "starter", "mileage_km": "120000"}, "mileage_type_or_range"),
        ({"title": "Не заводиться", "system": "starter", "price": 100}, "unexpected_keys:['price']"),
    ],
)
def test_manual_invalid_rejected(client, payload, expected_reason):
    # Готуємо один коректний запис, щоб перевірити незмінність уже збережених даних.
    client.post("/faults", json={"title": "Існуючий запис", "system": "battery"})
    count_before, items_before = snapshot(client)

    response = client.post("/faults", json=payload)
    assert response.status_code == 422
    body = response.json()
    assert body["status"] == "validation_error"
    assert body["reason"] == expected_reason

    count_after, items_after = snapshot(client)
    assert count_after == count_before
    assert items_after == items_before, "відмова не повинна змінювати ні кількість, ні вміст"
