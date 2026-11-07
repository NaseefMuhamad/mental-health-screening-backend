from typing import Literal

from pydantic import AwareDatetime, Field

from app.schemas._common import OutputModel


class OperationalSummary(OutputModel):
    scope: Literal["institution", "own_screenings", "submitted_screenings"]
    generated_at: AwareDatetime
    screening_sessions: int = Field(ge=0)
    draft: int = Field(ge=0)
    awaiting_review: int = Field(ge=0)
    in_review: int = Field(ge=0)
    reviewed: int = Field(ge=0)
    scheduled_followups: int = Field(ge=0)
    completed_followups: int = Field(ge=0)


from uuid import UUID
from app.schemas.prediction import CategoryLevel, PredictionStatus
from app.schemas.screening import ReviewStatus

class CounsellorQueueItem(OutputModel):
    id: UUID
    student_id: UUID
    student_code: str
    student_name: str
    measured_at: AwareDatetime
    review_status: ReviewStatus
    assigned_counsellor_id: UUID | None
    assigned_counsellor_name: str | None = None
    assigned_to_me: bool
    prediction_status: PredictionStatus
    assessment_complete: bool
    stress_level: CategoryLevel | None = None
    anxiety_level: CategoryLevel | None = None
    model_version: str | None = None
    generated_at: AwareDatetime | None = None


class ActivityDay(OutputModel):
    day: str
    screenings: int = Field(ge=0)

class ScreeningActivity(OutputModel):
    timezone: Literal["UTC"] = "UTC"
    items: list[ActivityDay]
