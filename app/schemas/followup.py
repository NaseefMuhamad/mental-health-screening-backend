"""Appointment status is independent of model output and screening review status."""

from enum import Enum
from uuid import UUID

from pydantic import AwareDatetime

from app.schemas._common import InputModel, NotesText, OutputModel, ShortText


class FollowupStatus(str, Enum):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class FollowupCreate(InputModel):
    screening_id: UUID
    scheduled_for: AwareDatetime
    reason: ShortText


class FollowupReschedule(InputModel):
    scheduled_for: AwareDatetime
    reason: ShortText


class FollowupComplete(InputModel):
    outcome: NotesText


class FollowupCancel(InputModel):
    reason: NotesText


class FollowupRead(OutputModel):
    id: UUID
    screening_id: UUID
    student_id: UUID
    counsellor_id: UUID
    scheduled_for: AwareDatetime
    reason: ShortText
    status: FollowupStatus
    outcome: NotesText | None = None
    cancellation_reason: NotesText | None = None
    completed_at: AwareDatetime | None = None
    cancelled_at: AwareDatetime | None = None
    created_at: AwareDatetime
