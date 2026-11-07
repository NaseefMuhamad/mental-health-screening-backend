from uuid import UUID

from fastapi import APIRouter, Query

from app.auth.permissions import CurrentUser, DatabaseSession
from app.schemas._common import Page
from app.schemas.screening import ReviewStatus, ScreeningAssignment, ScreeningCreate, ScreeningHandover, ScreeningRead, ScreeningOperationalRead
from app.services import screening_service


router = APIRouter(prefix="/screenings", tags=["Screenings"])


@router.post("", response_model=ScreeningRead, status_code=201)
def create_screening(payload: ScreeningCreate, db: DatabaseSession, user: CurrentUser):
    return screening_service.create_screening(db, payload, actor_id=user.id)


@router.get("", response_model=Page[ScreeningRead | ScreeningOperationalRead])
def list_screenings(db: DatabaseSession, user: CurrentUser, student_id: UUID | None = None,
                    review_status: ReviewStatus | None = None, assigned_only: bool = False, offset: int = Query(0, ge=0),
                    limit: int = Query(50, ge=1, le=100)):
    return screening_service.list_screenings(db, actor_id=user.id, student_id=student_id,
        review_status=review_status, assigned_only=assigned_only, offset=offset, limit=limit)


@router.get("/{screening_id}", response_model=ScreeningRead | ScreeningOperationalRead)
def get_screening(screening_id: UUID, db: DatabaseSession, user: CurrentUser):
    return screening_service.get_screening(db, screening_id, actor_id=user.id)


@router.post("/{screening_id}/submit", response_model=ScreeningRead)
def submit(screening_id: UUID, db: DatabaseSession, user: CurrentUser):
    return screening_service.submit_screening(db, screening_id, actor_id=user.id)


@router.put("/{screening_id}/assignment", response_model=ScreeningRead | ScreeningOperationalRead)
def assign(screening_id: UUID, payload: ScreeningAssignment, db: DatabaseSession, user: CurrentUser):
    return screening_service.assign_counsellor(db, screening_id, payload, actor_id=user.id)


@router.post("/{screening_id}/begin-review", response_model=ScreeningRead)
def begin_review(screening_id: UUID, db: DatabaseSession, user: CurrentUser):
    return screening_service.begin_review(db, screening_id, actor_id=user.id)


@router.post("/{screening_id}/handover", response_model=ScreeningRead | ScreeningOperationalRead)
def handover(screening_id: UUID, payload: ScreeningHandover, db: DatabaseSession, user: CurrentUser):
    return screening_service.handover_case(db, screening_id, payload, actor_id=user.id)


from app.schemas.assessment import AssessmentCreate, AssessmentRead
from app.services import assessment_service

@router.get("/{screening_id}/assessment", response_model=AssessmentRead | None)
def get_assessment(screening_id: UUID, db: DatabaseSession, user: CurrentUser):
    return assessment_service.get_latest(db,screening_id,actor_id=user.id)

@router.post("/{screening_id}/assessment", response_model=AssessmentRead, status_code=201)
def save_assessment(screening_id: UUID, payload: AssessmentCreate, db: DatabaseSession, user: CurrentUser):
    return assessment_service.create(db,screening_id,payload,actor_id=user.id)


@router.post("/{screening_id}/retry-prediction", response_model=ScreeningRead)
def retry_prediction(screening_id: UUID, db: DatabaseSession, user: CurrentUser):
    return screening_service.retry_prediction(db,screening_id,actor_id=user.id)
