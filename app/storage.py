"""Локальне сховище: один JSON-файл, лише читання і дозапис.

Модуль не перевіряє зміст полів — це робить app/policy.py.
"""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_PATH = "data/faults.json"


def storage_path() -> Path:
    return Path(os.getenv("FAULTLOG_STORAGE", DEFAULT_PATH))


def load() -> list[dict]:
    path = storage_path()
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    items = payload.get("items", [])
    return items if isinstance(items, list) else []


def append(fields: dict, source: str) -> dict:
    """Додає запис і повертає його. Попередні записи не змінюються й не перезаписуються."""
    record = {
        "id": str(uuid.uuid4()),
        "title": fields["title"],
        "system": fields["system"].value if hasattr(fields["system"], "value") else fields["system"],
        "mileage_km": fields["mileage_km"],
        "safety_stop": bool(fields["safety_stop"]),
        "source": source,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    items = load()
    items.append(record)
    _write(items)
    return record


def _write(items: list[dict]) -> None:
    path = storage_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump({"items": items}, handle, ensure_ascii=False, indent=1)
    os.replace(temporary, path)
