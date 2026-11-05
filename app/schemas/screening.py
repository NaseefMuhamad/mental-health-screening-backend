"""Separate screening events; prediction status and human review stay independent."""

from enum import Enum
from uuid import UUID

from pydantic import AwareDatetime

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


class ScreeningAssignment(InputModel):
    assigned_counsellor_id: UUID


class ScreeningRead(OutputModel):
    id: UUID
    student_id: UUID
    measured_at: AwareDatetime
    recorded_by: UUID
    assigned_counsellor_id: UUID | None = None
    review_status: ReviewStatus
    prediction_status: PredictionStatus
    measurements: MeasurementRead
    created_at: AwareDatetime
    submitted_at: AwareDatetime | None = None
