"""AI-компонент: лише отримання пропозиції.

Модуль не перевіряє пропозицію і не має доступу до сховища. Режим задається змінною
FAULTLOG_AI_MODE під час запуску сервісу (розділ 3.5 специфікації); параметрів запиту,
що впливають на перевірку чи збереження, у API немає.
"""

import json
import os
from pathlib import Path

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "scripted_proposals.json"
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_TIMEOUT = 30.0

SYSTEM_PROMPT = (
    "You turn a short Ukrainian driver message into a structured car fault record.\n"
    "Allowed system values: ['battery', 'starter', 'fuel', 'ignition', 'immobilizer'].\n"
    "Return one JSON object with keys: title (3-80 chars), system, mileage_km (integer or null), "
    "needs_clarification (boolean), clarification_question (string or null).\n"
    "Set system to null and needs_clarification to true when the message names no symptom of a "
    "specific system.\n"
    "Set mileage_km to null unless the message explicitly states the mileage number."
)


class AIUnavailable(RuntimeError):
    """Модель недоступна або перевищено час очікування."""


def ai_mode() -> str:
    return os.getenv("FAULTLOG_AI_MODE", "scripted").strip().lower()


def get_proposal(text: str) -> dict:
    """Повертає пропозицію як словник. Будь-яка проблема провайдера — AIUnavailable."""
    mode = ai_mode()
    if mode == "unavailable":
        raise AIUnavailable("ai_mode_unavailable")
    if mode == "scripted":
        return _scripted_proposal(text)
    if mode == "live":
        return _live_proposal(text)
    raise AIUnavailable(f"unknown_ai_mode:{mode}")


def _scripted_proposal(text: str) -> dict:
    with FIXTURE_PATH.open(encoding="utf-8") as handle:
        fixture = json.load(handle)
    key = " ".join(text.strip().lower().split())
    return fixture["proposals"].get(key, fixture["default"])


def _live_proposal(text: str) -> dict:
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise AIUnavailable("missing_api_key")

    timeout = float(os.getenv("FAULTLOG_AI_TIMEOUT", DEFAULT_TIMEOUT))
    model = os.getenv("FAULTLOG_AI_MODEL", DEFAULT_MODEL)
    client = OpenAI(api_key=api_key, timeout=timeout, max_retries=0)
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            response_format={"type": "json_object"},
            temperature=0,
            seed=42,
        )
        return json.loads(response.choices[0].message.content or "{}")
    except Exception as error:  # провайдер, мережа, таймаут, нечитабельний JSON
        raise AIUnavailable(type(error).__name__) from error
