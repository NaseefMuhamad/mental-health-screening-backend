from uuid import UUID

from fastapi import APIRouter, Query

from app.auth.permissions import CurrentUser, DatabaseSession
from app.schemas._common import Page
from app.schemas.student import StudentCreate, StudentRead, StudentUpdate
from app.services import student_service


router = APIRouter(prefix="/students", tags=["Students"])


@router.post("", response_model=StudentRead, status_code=201)
def create_student(payload: StudentCreate, db: DatabaseSession, user: CurrentUser):
    return student_service.create_student(db, payload, actor_id=user.id)


@router.get("", response_model=Page[StudentRead])
def list_students(db: DatabaseSession, user: CurrentUser, search: str = Query("", max_length=120),
                  offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
    return student_service.list_students(db, actor_id=user.id, search=search, offset=offset, limit=limit)


@router.get("/{student_id}", response_model=StudentRead)
def get_student(student_id: UUID, db: DatabaseSession, user: CurrentUser):
    return student_service.get_student(db, student_id, actor_id=user.id)


@router.patch("/{student_id}", response_model=StudentRead)
def update_student(student_id: UUID, payload: StudentUpdate, db: DatabaseSession, user: CurrentUser):
    return student_service.update_student(db, student_id, payload, actor_id=user.id)
