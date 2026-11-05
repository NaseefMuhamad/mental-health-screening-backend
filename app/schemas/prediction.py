"""Prediction contracts without assuming stress/anxiety classes or ML features."""

from enum import Enum
from uuid import UUID

from pydantic import AwareDatetime, model_validator
from typing_extensions import Self

from app.schemas._common import InputModel, NotesText, OutputModel, ShortText


class PredictionStatus(str, Enum):
    UNAVAILABLE = "unavailable"
    PROCESSING = "processing"
    AVAILABLE = "available"
    FAILED = "failed"


class PredictionRequest(InputModel):
    """Backend retrieves validated measurements; clients do not supply outputs."""

    screening_id: UUID


class PredictionRead(OutputModel):
    screening_id: UUID
    status: PredictionStatus
    indication: NotesText | None = None
    model_version: ShortText | None = None
    generated_at: AwareDatetime | None = None
    message: ShortText | None = None

    @model_validator(mode="after")
    def require_actual_output(self) -> Self:
        if self.status == PredictionStatus.AVAILABLE:
            if self.indication is None or self.model_version is None or self.generated_at is None:
                raise ValueError("Available predictions need an indication, model version and generation time.")
        elif any(value is not None for value in (self.indication, self.model_version, self.generated_at)):
            raise ValueError("Unavailable, processing or failed predictions must not contain model outputs.")
        return self
