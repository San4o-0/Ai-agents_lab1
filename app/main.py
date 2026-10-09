"""HTTP-обробники. Правила перевірки — в app/policy.py, збереження — в app/storage.py."""

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app import ai, policy, storage
from app.models import FromTextIn, ManualFaultIn

# Значення з .env заповнюють лише те, що не задано у середовищі запуску.
load_dotenv(override=False)

app = FastAPI(title="Журнал несправностей авто", version="1.0.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "ai_mode": ai.ai_mode()}


@app.get("/faults")
def list_faults() -> dict:
    items = storage.load()
    return {"count": len(items), "items": items}


@app.post("/faults")
async def create_manual(payload: dict) -> JSONResponse:
    """Ручний шлях. Модель не викликається за жодного значення FAULTLOG_AI_MODE."""
    try:
        manual = ManualFaultIn.model_validate(payload)
    except ValidationError as error:
        return JSONResponse(
            status_code=422,
            content={"status": "validation_error", "reason": policy.manual_reason(error)},
        )

    record = storage.append(
        {
            "title": manual.title.strip(),
            "system": manual.system,
            "mileage_km": manual.mileage_km,
            "safety_stop": manual.safety_stop,
        },
        source="manual",
    )
    return JSONResponse(status_code=201, content={"status": "created", "record": record})


@app.post("/faults/from-text")
async def create_from_text(payload: dict) -> JSONResponse:
    """Порядок перевірок із розділу 2.4 специфікації."""
    try:
        request = FromTextIn.model_validate(payload)
    except ValidationError:
        return JSONResponse(
            status_code=422, content={"status": "validation_error", "reason": "text_length"}
        )

    text = request.text

    # 1. Ознака небезпеки — до звернення до моделі.
    if policy.detect_danger(text):
        return JSONResponse(
            status_code=422,
            content={
                "status": policy.STATUS_SAFETY_HOLD,
                "reason": "danger_markers_in_text",
                "message": policy.SAFETY_MESSAGE,
            },
        )

    # 2. Отримання пропозиції. Недоступність моделі не змінює дані.
    try:
        proposal = ai.get_proposal(text)
    except ai.AIUnavailable as error:
        return JSONResponse(
            status_code=503, content={"status": "ai_unavailable", "reason": str(error)}
        )

    # 3. Схема, невизначеність і зміст.
    status, reason, fields = policy.validate_proposal(text, proposal)

    if status == policy.STATUS_NEEDS_CLARIFICATION:
        return JSONResponse(
            status_code=422,
            content={
                "status": status,
                "reason": reason,
                "question": policy.clarification_question(proposal),
            },
        )
    if status != policy.STATUS_CREATED:
        return JSONResponse(status_code=422, content={"status": status, "reason": reason})

    # 4. Збереження лише після успішної перевірки.
    record = storage.append(fields, source="ai")
    return JSONResponse(
        status_code=201, content={"status": "created", "record": record, "proposal": proposal}
    )
