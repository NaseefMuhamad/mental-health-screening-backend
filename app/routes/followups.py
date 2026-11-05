from uuid import UUID

from fastapi import APIRouter, Query

from app.auth.permissions import CounsellorUser, DatabaseSession
from app.schemas._common import Page
from app.schemas.followup import (
    FollowupCancel, FollowupComplete, FollowupCreate, FollowupRead, FollowupReschedule, FollowupStatus,
)
from app.services import followup_service


router = APIRouter(prefix="/followups", tags=["Follow-ups"])


@router.post("", response_model=FollowupRead, status_code=201)
def create(payload: FollowupCreate, db: DatabaseSession, user: CounsellorUser):
    return followup_service.create_followup(db, payload, actor_id=user.id)


@router.get("", response_model=Page[FollowupRead])
def list_followups(db: DatabaseSession, user: CounsellorUser, status: FollowupStatus | None = None,
                   due: bool = False, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
    return followup_service.list_followups(db, actor_id=user.id, status=status, due=due, offset=offset, limit=limit)


@router.get("/{followup_id}", response_model=FollowupRead)
def get(followup_id: UUID, db: DatabaseSession, user: CounsellorUser):
    return followup_service.get_followup(db, followup_id, actor_id=user.id)


@router.patch("/{followup_id}", response_model=FollowupRead)
def reschedule(followup_id: UUID, payload: FollowupReschedule, db: DatabaseSession, user: CounsellorUser):
    return followup_service.reschedule_followup(db, followup_id, payload, actor_id=user.id)


@router.post("/{followup_id}/complete", response_model=FollowupRead)
def complete(followup_id: UUID, payload: FollowupComplete, db: DatabaseSession, user: CounsellorUser):
    return followup_service.complete_followup(db, followup_id, payload, actor_id=user.id)


@router.post("/{followup_id}/cancel", response_model=FollowupRead)
def cancel(followup_id: UUID, payload: FollowupCancel, db: DatabaseSession, user: CounsellorUser):
    return followup_service.cancel_followup(db, followup_id, payload, actor_id=user.id)
