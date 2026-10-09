"""Моделі даних сервісу. Межі полів — з розділу 1 специфікації."""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TITLE_MIN = 3
TITLE_MAX = 80
MILEAGE_MAX = 2_000_000
TEXT_MIN = 3
TEXT_MAX = 500


class System(str, Enum):
    battery = "battery"
    starter = "starter"
    fuel = "fuel"
    ignition = "ignition"
    immobilizer = "immobilizer"


class ManualFaultIn(BaseModel):
    """Тіло POST /faults. Зайві поля заборонені, щоб вхід не розширювався непомітно."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=TITLE_MIN, max_length=TITLE_MAX)
    system: System
    mileage_km: int | None = Field(default=None, ge=0, le=MILEAGE_MAX, strict=True)
    safety_stop: bool = False


class FromTextIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=TEXT_MIN, max_length=TEXT_MAX)


class FaultRecord(BaseModel):
    id: str
    title: str
    system: System
    mileage_km: int | None
    safety_stop: bool
    source: Literal["manual", "ai"]
    created_at: str


class Proposal(BaseModel):
    """Схема пропозиції AI-компонента (розділ 3.1 специфікації)."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    system: System | None = None
    mileage_km: int | None = Field(default=None, ge=0, le=MILEAGE_MAX, strict=True)
    needs_clarification: bool = False
    clarification_question: str | None = None
