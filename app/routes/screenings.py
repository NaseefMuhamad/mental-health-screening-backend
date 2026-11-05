from uuid import UUID

from fastapi import APIRouter, Query

from app.auth.permissions import CurrentUser, DatabaseSession
from app.schemas._common import Page
from app.schemas.screening import ReviewStatus, ScreeningAssignment, ScreeningCreate, ScreeningHandover, ScreeningRead
from app.services import screening_service


router = APIRouter(prefix="/screenings", tags=["Screenings"])


@router.post("", response_model=ScreeningRead, status_code=201)
def create_screening(payload: ScreeningCreate, db: DatabaseSession, user: CurrentUser):
    return screening_service.create_screening(db, payload, actor_id=user.id)


@router.get("", response_model=Page[ScreeningRead])
def list_screenings(db: DatabaseSession, user: CurrentUser, student_id: UUID | None = None,
                    review_status: ReviewStatus | None = None, offset: int = Query(0, ge=0),
                    limit: int = Query(50, ge=1, le=100)):
    return screening_service.list_screenings(db, actor_id=user.id, student_id=student_id,
        review_status=review_status, offset=offset, limit=limit)


@router.get("/{screening_id}", response_model=ScreeningRead)
def get_screening(screening_id: UUID, db: DatabaseSession, user: CurrentUser):
    return screening_service.get_screening(db, screening_id, actor_id=user.id)


@router.post("/{screening_id}/submit", response_model=ScreeningRead)
def submit(screening_id: UUID, db: DatabaseSession, user: CurrentUser):
    return screening_service.submit_screening(db, screening_id, actor_id=user.id)


@router.put("/{screening_id}/assignment", response_model=ScreeningRead)
def assign(screening_id: UUID, payload: ScreeningAssignment, db: DatabaseSession, user: CurrentUser):
    return screening_service.assign_counsellor(db, screening_id, payload, actor_id=user.id)


@router.post("/{screening_id}/begin-review", response_model=ScreeningRead)
def begin_review(screening_id: UUID, db: DatabaseSession, user: CurrentUser):
    return screening_service.begin_review(db, screening_id, actor_id=user.id)


@router.post("/{screening_id}/handover", response_model=ScreeningRead)
def handover(screening_id: UUID, payload: ScreeningHandover, db: DatabaseSession, user: CurrentUser):
    return screening_service.handover_case(db, screening_id, payload, actor_id=user.id)
