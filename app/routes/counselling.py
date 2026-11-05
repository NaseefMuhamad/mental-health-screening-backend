from uuid import UUID

from fastapi import APIRouter, Query

from app.auth.permissions import CounsellorUser, DatabaseSession
from app.schemas._common import Page
from app.schemas.counselling import CounsellingCreate, CounsellingRead
from app.services import counselling_service


router = APIRouter(prefix="/counselling", tags=["Counsellor review"])


@router.post("", response_model=CounsellingRead, status_code=201)
def create_record(payload: CounsellingCreate, db: DatabaseSession, user: CounsellorUser):
    return counselling_service.create_record(db, payload, actor_id=user.id)


@router.get("", response_model=Page[CounsellingRead])
def list_records(db: DatabaseSession, user: CounsellorUser, screening_id: UUID | None = None,
                 offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
    return counselling_service.list_records(db, actor_id=user.id, screening_id=screening_id, offset=offset, limit=limit)
