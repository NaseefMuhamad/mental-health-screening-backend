from typing import Literal

from pydantic import AwareDatetime, Field

from app.schemas._common import OutputModel


class OperationalSummary(OutputModel):
    scope: Literal["institution", "own_screenings", "assigned_cases"]
    generated_at: AwareDatetime
    screening_sessions: int = Field(ge=0)
    draft: int = Field(ge=0)
    awaiting_review: int = Field(ge=0)
    in_review: int = Field(ge=0)
    reviewed: int = Field(ge=0)
    scheduled_followups: int = Field(ge=0)
    completed_followups: int = Field(ge=0)
