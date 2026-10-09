"""Детерміновані правила сервісу.

Модуль не знає ні про HTTP, ні про сховище, ні про провайдера: ті самі правила перевіряються
і без запущеного сервера. Правила перенесені з висновку notebooks/01_experiment.ipynb.
"""

import re

from pydantic import ValidationError

from app.models import MILEAGE_MAX, TITLE_MAX, TITLE_MIN, Proposal, System

DANGER_MARKERS = (
    "дим",
    "пахне бензин",
    "запах бензин",
    "пахне палив",
    "іскр",
    "тече бензин",
)

DEFAULT_QUESTION = "Який симптом спостерігається при спробі завести?"
SAFETY_MESSAGE = (
    "Виявлено ознаки небезпеки. Не намагайтеся заводити автомобіль — "
    "запис передано фахівцю."
)

STATUS_CREATED = "created"
STATUS_NEEDS_CLARIFICATION = "needs_clarification"
STATUS_SAFETY_HOLD = "safety_hold"
STATUS_CONTENT_REJECTED = "content_rejected"
STATUS_INVALID_PROPOSAL = "invalid_proposal"


def detect_danger(text: str) -> bool:
    """Ознака небезпеки визначається програмою, а не моделлю (рішення C-2, C-5)."""
    low = text.lower()
    return any(marker in low for marker in DANGER_MARKERS)


def mileage_supported_by_text(text: str, mileage: int) -> bool:
    """Пробіг приймається лише тоді, коли те саме число є в повідомленні (рішення C-4)."""
    digits = re.sub(r"\D", "", text)
    if str(mileage) in digits:
        return True
    if mileage % 1000 == 0 and "тис" in text.lower() and str(mileage // 1000) in digits:
        return True
    return False


def validate_proposal(text: str, raw_proposal: object) -> tuple[str, str, dict | None]:
    """Повертає (status, reason, поля запису або None).

    Порядок перевірок — з розділу 2.4 специфікації: схема → невизначеність → зміст.
    Перевірку небезпеки виконують раніше, до звернення до моделі.
    """
    if not isinstance(raw_proposal, dict):
        return STATUS_INVALID_PROPOSAL, "proposal_is_not_object", None

    try:
        proposal = Proposal.model_validate(raw_proposal)
    except ValidationError as error:
        return STATUS_INVALID_PROPOSAL, _schema_reason(error, raw_proposal), None

    title = proposal.title.strip() if proposal.title else None
    if title is not None and not TITLE_MIN <= len(title) <= TITLE_MAX:
        return STATUS_INVALID_PROPOSAL, "title_length_or_type", None

    if proposal.needs_clarification or not title or proposal.system is None:
        return STATUS_NEEDS_CLARIFICATION, "system_or_title_missing", None

    if proposal.mileage_km is not None and not mileage_supported_by_text(text, proposal.mileage_km):
        return STATUS_CONTENT_REJECTED, f"mileage_not_in_text:{proposal.mileage_km}", None

    fields = {
        "title": title,
        "system": proposal.system,
        "mileage_km": proposal.mileage_km,
        # AI-шлях ніколи не ставить safety_stop: true (рішення C-3).
        "safety_stop": False,
    }
    return STATUS_CREATED, "ok", fields


def clarification_question(raw_proposal: object) -> str:
    if isinstance(raw_proposal, dict):
        question = raw_proposal.get("clarification_question")
        if isinstance(question, str) and question.strip():
            return question.strip()
    return DEFAULT_QUESTION


def manual_reason(error: ValidationError) -> str:
    """Машинна причина відмови ручного входу (розділ 5 специфікації)."""
    first = error.errors()[0]
    field = ".".join(str(part) for part in first["loc"]) or "body"
    # Тип помилки перевіряємо раніше за назву поля: відсутнє поле і поле неправильної
    # довжини — різні причини відмови (знайдено тестом test_manual_invalid_rejected).
    if first["type"] == "missing":
        return f"missing_field:{field}"
    if first["type"] == "extra_forbidden":
        return f"unexpected_keys:['{field}']"
    if field == "system":
        return f"system_not_allowed:{first.get('input')}"
    if field == "title":
        return "title_length_or_type"
    if field == "mileage_km":
        return "mileage_type_or_range"
    return f"invalid_field:{field}"


def _schema_reason(error: ValidationError, raw_proposal: dict) -> str:
    allowed = set(Proposal.model_fields)
    unexpected = sorted(set(raw_proposal) - allowed)
    if unexpected:
        return f"unexpected_keys:{unexpected}"

    first = error.errors()[0]
    field = ".".join(str(part) for part in first["loc"])
    if field == "system":
        return f"system_not_allowed:{raw_proposal.get('system')}"
    if field == "title":
        return "title_length_or_type"
    if field == "mileage_km":
        return "mileage_type_or_range"
    return f"invalid_field:{field}"


ALLOWED_SYSTEMS = tuple(item.value for item in System)
MILEAGE_LIMIT = MILEAGE_MAX
