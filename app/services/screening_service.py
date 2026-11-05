"""New sessions, visibility, submission, assignment and beginning human review."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.entities import Measurement, Screening, Student, User, utc_now
from app.schemas.screening import ReviewStatus, ScreeningAssignment, ScreeningCreate, ScreeningRead
from app.schemas.user import UserRole
from app.services._common import (
    audit, load_screening, require_actor, screening_visibility, validate_page, write_operation,
)
from app.services.errors import Conflict, InvalidOperation, NotFound


def create_screening(db: Session, payload: ScreeningCreate, *, actor_id: UUID) -> ScreeningRead:
    with write_operation(db):
        actor = require_actor(db, actor_id, {UserRole.SCREENING_PERSONNEL})
        if db.get(Student, payload.student_id) is None:
            raise NotFound("Student not found.")
        screening = Screening(
            student_id=payload.student_id, measured_at=payload.measured_at,
            recorded_by=actor.id, review_status="draft", prediction_status="unavailable",
        )
        screening.measurements = Measurement(**payload.measurements.model_dump(), recorded_by=actor.id)
        db.add(screening)
        db.flush()
        response = ScreeningRead.model_validate(screening)
        audit(db, actor.id, "screening.created", "screening", screening.id)
    return response


def get_screening(db: Session, screening_id: UUID, *, actor_id: UUID) -> ScreeningRead:
    actor = require_actor(db, actor_id, set(UserRole))
    return ScreeningRead.model_validate(load_screening(db, screening_id, actor))


def list_screenings(
    db: Session, *, actor_id: UUID, student_id: UUID | None = None,
    review_status: ReviewStatus | None = None, offset: int = 0, limit: int = 50,
) -> dict:
    actor = require_actor(db, actor_id, set(UserRole))
    validate_page(offset, limit)
    if review_status is not None:
        try:
            review_status = ReviewStatus(review_status)
        except ValueError:
            raise InvalidOperation("Unknown review status.") from None
    statement = select(Screening).where(screening_visibility(actor))
    if student_id is not None:
        statement = statement.where(Screening.student_id == student_id)
    if review_status is not None:
        statement = statement.where(Screening.review_status == review_status.value)
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    records = db.scalars(statement.order_by(Screening.created_at.desc(), Screening.id).offset(offset).limit(limit)).all()
    return {"items": [ScreeningRead.model_validate(item) for item in records], "total": total, "offset": offset, "limit": limit}


def submit_screening(db: Session, screening_id: UUID, *, actor_id: UUID) -> ScreeningRead:
    with write_operation(db):
        actor = require_actor(db, actor_id, {UserRole.SCREENING_PERSONNEL})
        screening = load_screening(db, screening_id, actor, lock=True)
        if screening.review_status == "draft":
            screening.review_status = "awaiting_review"
            screening.submitted_at = utc_now()
            audit(db, actor.id, "screening.submitted", "screening", screening.id)
        elif screening.review_status != "awaiting_review":
            raise Conflict("Only draft screenings can be submitted for review.")
        db.flush()
        response = ScreeningRead.model_validate(screening)
    return response


def assign_counsellor(
    db: Session, screening_id: UUID, payload: ScreeningAssignment, *, actor_id: UUID,
) -> ScreeningRead:
    with write_operation(db):
        actor = require_actor(db, actor_id, {UserRole.ADMINISTRATOR})
        screening = load_screening(db, screening_id, actor, lock=True)
        if screening.review_status != "awaiting_review":
            raise Conflict("Assign a counsellor after submission and before review begins.")
        counsellor = db.scalar(select(User).where(
            User.id == payload.assigned_counsellor_id, User.role == UserRole.COUNSELLOR,
            User.is_active.is_(True),
        ).with_for_update().execution_options(populate_existing=True))
        if counsellor is None:
            raise InvalidOperation("Choose an active counsellor.")
        if screening.assigned_counsellor_id != counsellor.id:
            screening.assigned_counsellor_id = counsellor.id
            audit(db, actor.id, "screening.assigned", "screening", screening.id)
        db.flush()
        response = ScreeningRead.model_validate(screening)
    return response


def begin_review(db: Session, screening_id: UUID, *, actor_id: UUID) -> ScreeningRead:
    with write_operation(db):
        actor = require_actor(db, actor_id, {UserRole.COUNSELLOR})
        screening = load_screening(db, screening_id, actor, lock=True)
        if screening.review_status == "awaiting_review":
            screening.review_status = "in_review"
            audit(db, actor.id, "screening.review_started", "screening", screening.id)
        elif screening.review_status != "in_review":
            raise Conflict("This screening cannot begin review in its current state.")
        db.flush()
        response = ScreeningRead.model_validate(screening)
    return response
