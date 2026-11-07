"""Separate screening events; prediction status and human review stay independent."""

from enum import Enum
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator
from app.schemas.assessment import AssessmentCreate

from app.schemas._common import InputModel,NotesText ,OutputModel
from app.schemas.measurement import MeasurementCreate, MeasurementRead
from app.schemas.prediction import PredictionStatus


class ReviewStatus(str, Enum):
    DRAFT = "draft"
    AWAITING_REVIEW = "awaiting_review"
    IN_REVIEW = "in_review"
    REVIEWED = "reviewed"
class ScreeningHandover(InputModel):
    assigned_counsellor_id: UUID
    reason: NotesText

class ScreeningCreate(InputModel):
    """Create a new event. IDs, recorder, assignment and statuses are server-owned."""

    student_id: UUID
    measured_at: AwareDatetime
    measurements: MeasurementCreate
    assessment: AssessmentCreate | None = None
    submit_for_review: bool = Field(default=False, strict=True)

    @model_validator(mode="after")
    def require_complete_submission(self):
        if self.submit_for_review and self.assessment is None:
            raise ValueError("Complete all five screening questions before submission.")
        return self


class ScreeningAssignment(InputModel):
    assigned_counsellor_id: UUID


class ScreeningOperationalRead(OutputModel):
    student_name: str | None = None
    student_code: str | None = None
    id: UUID
    student_id: UUID
    measured_at: AwareDatetime
    recorded_by: UUID
    assigned_counsellor_id: UUID | None = None
    assigned_counsellor_name: str | None = None
    review_status: ReviewStatus
    prediction_status: PredictionStatus
    created_at: AwareDatetime
    submitted_at: AwareDatetime | None = None


class ScreeningRead(ScreeningOperationalRead):
    measurements: MeasurementRead
