"""AC-2…AC-5: AI-шлях із фіксованими пропозиціями та імітованим збоєм.

Джерело пропозиції підмінене всередині сервісу (FAULTLOG_AI_MODE=scripted / unavailable).
Обробники, перевірка і збереження — ті самі, що у звичайному запуску.
"""

from tests.conftest import snapshot

VALID_TEXT = "Стартер лише клацає, світло на панелі яскраве, пробіг 120000 км"
VALID_TEXT_THOUSANDS = "Бак порожній, мотор крутить і не схоплює, 85 тис. км"
CONTENT_REJECT_TEXT = "Стартер клацає, світло на панелі яскраве"  # пропозиція вигадує 150000
INVALID_SCHEMA_TEXT = "Акумулятор сів, на панелі нічого не світиться"  # system поза списком
INCOMPLETE_TEXT = "Машина не їде, зробіть щось"
DANGER_TEXT = "Після спроби завести з-під капота йде дим і сильно пахне бензином"


def test_valid_proposal_creates_one_record(client):
    count_before, _ = snapshot(client)

    response = client.post("/faults/from-text", json={"text": VALID_TEXT})
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "created"

    record = body["record"]
    assert record["system"] == "starter"
    assert record["mileage_km"] == 120000
    assert record["source"] == "ai"
    assert record["safety_stop"] is False

    count_after, items_after = snapshot(client)
    assert count_after == count_before + 1, "має з'явитися рівно один новий запис"
    stored = [item for item in items_after if item["id"] == record["id"]]
    assert stored == [record], "запис у відповіді має збігатися із записом у списку"


def test_valid_proposal_accepts_thousands_notation(client):
    response = client.post("/faults/from-text", json={"text": VALID_TEXT_THOUSANDS})
    assert response.status_code == 201
    assert response.json()["record"]["mileage_km"] == 85000


def test_needs_clarification_not_saved(client):
    count_before, items_before = snapshot(client)

    response = client.post("/faults/from-text", json={"text": INCOMPLETE_TEXT})
    assert response.status_code == 422
    body = response.json()
    assert body["status"] == "needs_clarification"
    assert body["question"], "відповідь має містити питання для уточнення"
    assert "record" not in body

    assert snapshot(client) == (count_before, items_before)


def test_safety_hold_before_model(client, monkeypatch):
    # Якщо модель усе ж буде викликана, тест упаде: джерело пропозиції кидає помилку.
    def fail(_text):
        raise AssertionError("модель не повинна викликатися для тексту з ознакою небезпеки")

    monkeypatch.setattr("app.ai.get_proposal", fail)
    count_before, items_before = snapshot(client)

    response = client.post("/faults/from-text", json={"text": DANGER_TEXT})
    assert response.status_code == 422
    body = response.json()
    assert body["status"] == "safety_hold"
    assert body["reason"] == "danger_markers_in_text"
    assert body["message"]

    assert snapshot(client) == (count_before, items_before)


def test_invalid_proposal_rejected(client):
    count_before, items_before = snapshot(client)

    response = client.post("/faults/from-text", json={"text": INVALID_SCHEMA_TEXT})
    assert response.status_code == 422
    body = response.json()
    assert body["status"] == "invalid_proposal"
    assert body["reason"] == "system_not_allowed:engine_block"

    assert snapshot(client) == (count_before, items_before)


def test_content_rejected_mileage_not_in_text(client):
    count_before, items_before = snapshot(client)

    response = client.post("/faults/from-text", json={"text": CONTENT_REJECT_TEXT})
    assert response.status_code == 422
    body = response.json()
    assert body["status"] == "content_rejected"
    assert body["reason"] == "mileage_not_in_text:150000"

    assert snapshot(client) == (count_before, items_before)


def test_validator_is_sensitive_to_wrong_value(client):
    """Чутливість перевірки: пропозиції відрізняються лише значенням пробігу."""
    created = client.post("/faults/from-text", json={"text": VALID_TEXT})
    rejected = client.post("/faults/from-text", json={"text": CONTENT_REJECT_TEXT})

    assert created.status_code == 201
    assert created.json()["record"]["mileage_km"] == 120000
    # Той самий вузол starter, та сама схема, але число не згадане в тексті.
    assert rejected.status_code == 422
    assert rejected.json()["status"] == "content_rejected"

    count, items = snapshot(client)
    assert count == 1, "хибна пропозиція не повинна додавати другий запис"
    assert items[0]["mileage_km"] == 120000


def test_empty_text_rejected(client):
    count_before, items_before = snapshot(client)
    response = client.post("/faults/from-text", json={"text": ""})
    assert response.status_code == 422
    assert response.json() == {"status": "validation_error", "reason": "text_length"}
    assert snapshot(client) == (count_before, items_before)


def test_ai_unavailable_keeps_data(client, monkeypatch):
    client.post("/faults", json={"title": "Запис до збою", "system": "battery"})
    count_before, items_before = snapshot(client)

    monkeypatch.setenv("FAULTLOG_AI_MODE", "unavailable")
    response = client.post("/faults/from-text", json={"text": VALID_TEXT})
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "ai_unavailable"
    assert body["reason"] == "ai_mode_unavailable"

    assert snapshot(client) == (count_before, items_before)


def test_manual_path_works_after_ai_failure(client, monkeypatch):
    monkeypatch.setenv("FAULTLOG_AI_MODE", "unavailable")
    assert client.post("/faults/from-text", json={"text": VALID_TEXT}).status_code == 503

    count_before, _ = snapshot(client)
    response = client.post(
        "/faults", json={"title": "Ручний запис після збою", "system": "starter"}
    )
    assert response.status_code == 201
    record = response.json()["record"]

    count_after, items_after = snapshot(client)
    assert count_after == count_before + 1
    assert [item for item in items_after if item["id"] == record["id"]] == [record]
