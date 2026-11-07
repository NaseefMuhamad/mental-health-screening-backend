"""Human review actions and restricted notes; never a model-generated diagnosis."""

from enum import Enum
from uuid import UUID

from pydantic import AwareDatetime

from app.schemas._common import InputModel, NotesText, OutputModel


class CounsellingAction(str, Enum):
    COUNSELLING_SCHEDULED = "counselling_scheduled"
    FURTHER_ASSESSMENT = "further_assessment_recommended"
    REFERRAL = "referral_made"
    FOLLOWUP_REQUIRED = "followup_required"
    NO_IMMEDIATE_ACTION = "no_immediate_action_required"


class CounsellingCreate(InputModel):
    screening_id: UUID
    action: CounsellingAction
    occurred_at: AwareDatetime
    notes: NotesText | None = None


class CounsellingRead(OutputModel):
    student_name: str | None = None
    student_code: str | None = None
    """Return only to an authorised counsellor/reviewer, not general staff lists."""

    id: UUID
    screening_id: UUID
    reviewer_id: UUID
    action: CounsellingAction
    occurred_at: AwareDatetime
    notes: NotesText | None = None
    created_at: AwareDatetime
