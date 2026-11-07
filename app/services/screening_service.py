"""New sessions, visibility, submission, assignment and beginning human review."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.entities import Measurement, Screening, Student, User, utc_now
from app.schemas.screening import ReviewStatus, ScreeningAssignment, ScreeningCreate, ScreeningRead, ScreeningOperationalRead, ScreeningHandover
from app.schemas.user import UserRole
from app.services._common import (
    audit, load_screening, load_assigned_screening, require_actor, screening_visibility, validate_page, write_operation,
)
from app.services.errors import Conflict, InvalidOperation, NotFound


def screening_response(screening, actor):
    model = ScreeningOperationalRead if actor.role == UserRole.ADMINISTRATOR else ScreeningRead
    return model.model_validate(screening)


def create_screening(db: Session, payload: ScreeningCreate, *, actor_id: UUID) -> ScreeningRead:
    from app.services import assessment_service
    with write_operation(db):
        actor = require_actor(db, actor_id, {UserRole.SCREENING_PERSONNEL})
        if db.get(Student, payload.student_id) is None:
            raise NotFound("Student not found.")
        screening = Screening(student_id=payload.student_id, measured_at=payload.measured_at,
            recorded_by=actor.id, review_status="draft", prediction_status="unavailable")
        screening.measurements = Measurement(**payload.measurements.model_dump(), recorded_by=actor.id)
        db.add(screening); db.flush()
        audit(db, actor.id, "screening.created", "screening", screening.id)
        if payload.assessment is not None:
            assessment_service.append_snapshot(db,screening,actor,payload.assessment)
        if payload.submit_for_review:
            screening.review_status="awaiting_review";screening.submitted_at=utc_now()
            audit(db,actor.id,"screening.submitted","screening",screening.id)
        screening_id=screening.id
    if payload.submit_for_review:
        from app.services.prediction_service import generate_after_submission
        generate_after_submission(db,screening_id,actor_id=actor_id)
    return get_screening(db,screening_id,actor_id=actor_id)


def get_screening(db: Session, screening_id: UUID, *, actor_id: UUID) -> ScreeningRead:
    actor = require_actor(db, actor_id, set(UserRole))
    return screening_response(load_screening(db, screening_id, actor), actor)


def list_screenings(
    db: Session, *, actor_id: UUID, student_id: UUID | None = None,
    review_status: ReviewStatus | None = None, assigned_only: bool = False, offset: int = 0, limit: int = 50,
) -> dict:
    actor = require_actor(db, actor_id, set(UserRole))
    validate_page(offset, limit)
    if review_status is not None:
        try:
            review_status = ReviewStatus(review_status)
        except ValueError:
            raise InvalidOperation("Unknown review status.") from None
    statement = select(Screening).where(screening_visibility(actor))
    if assigned_only:
        if actor.role != UserRole.COUNSELLOR:
            raise InvalidOperation("The personal case filter is for counsellors.")
        statement = statement.where(Screening.assigned_counsellor_id == actor.id)
    if student_id is not None:
        statement = statement.where(Screening.student_id == student_id)
    if review_status is not None:
        statement = statement.where(Screening.review_status == review_status.value)
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    records = db.scalars(statement.order_by(Screening.created_at.desc(), Screening.id).offset(offset).limit(limit)).all()
    return {"items": [screening_response(item, actor) for item in records], "total": total, "offset": offset, "limit": limit}


def submit_screening(db: Session, screening_id: UUID, *, actor_id: UUID) -> ScreeningRead:
    from app.services.assessment_service import latest
    with write_operation(db):
        actor = require_actor(db, actor_id, {UserRole.SCREENING_PERSONNEL})
        screening = load_screening(db, screening_id, actor, lock=True)
        if screening.review_status == "draft":
            if latest(db,screening.id) is None:
                raise Conflict("Complete the five screening questions before submitting this draft.")
            screening.review_status = "awaiting_review";screening.submitted_at = utc_now()
            audit(db, actor.id, "screening.submitted", "screening", screening.id)
        elif screening.review_status != "awaiting_review":
            raise Conflict("Only draft screenings can be submitted for review.")
    from app.services.prediction_service import generate_after_submission
    generate_after_submission(db,screening_id,actor_id=actor_id)
    return get_screening(db,screening_id,actor_id=actor_id)


def retry_prediction(db: Session, screening_id: UUID, *, actor_id: UUID) -> ScreeningRead:
    actor=require_actor(db,actor_id,{UserRole.SCREENING_PERSONNEL})
    screening=load_screening(db,screening_id,actor)
    if screening.review_status=='draft':raise Conflict("Submit the screening before requesting predictions.")
    from app.services.prediction_service import generate_after_submission
    generate_after_submission(db,screening_id,actor_id=actor_id)
    return get_screening(db,screening_id,actor_id=actor_id)


def assign_counsellor(
    db: Session, screening_id: UUID, payload: ScreeningAssignment, *, actor_id: UUID,
) -> ScreeningRead:
    from app.services.auth_service import _staff_lock
    with write_operation(db):
        _staff_lock(db)
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
        db.expire(screening,["assigned_counsellor"])
        response = screening_response(screening, actor)
    return response


def begin_review(db: Session, screening_id: UUID, *, actor_id: UUID) -> ScreeningRead:
    """Take an unclaimed submitted case and begin counselling in one transaction."""
    from sqlalchemy import update
    from app.services.auth_service import _staff_lock
    with write_operation(db):
        _staff_lock(db)
        actor=require_actor(db,actor_id,{UserRole.COUNSELLOR})
        claimed=db.execute(update(Screening).where(
            Screening.id==screening_id, Screening.assigned_counsellor_id.is_(None),
            Screening.review_status=="awaiting_review",
        ).values(assigned_counsellor_id=actor.id,review_status="in_review")).rowcount
        screening=load_screening(db,screening_id,actor,lock=True)
        if screening.assigned_counsellor_id != actor.id:
            raise Conflict("Another counsellor is handling this case. Ask the administrator for a transfer if needed.")
        if claimed:
            audit(db,actor.id,"screening.claimed","screening",screening.id)
            audit(db,actor.id,"screening.review_started","screening",screening.id)
        elif screening.review_status=="awaiting_review":
            screening.review_status="in_review"
            audit(db,actor.id,"screening.review_started","screening",screening.id)
        elif screening.review_status!="in_review":
            raise Conflict("This case has already been reviewed.")
        db.flush();response=screening_response(screening,actor)
    return response


def handover_case(db: Session, screening_id: UUID, payload: ScreeningHandover, *, actor_id: UUID) -> ScreeningRead:
    """Administrator handover preserves prior reviews and completed appointments."""
    from sqlalchemy import update
    from app.database.entities import CaseHandover, Followup
    from app.services.auth_service import _staff_lock

    with write_operation(db):
        _staff_lock(db)
        actor = require_actor(db, actor_id, {UserRole.ADMINISTRATOR})
        screening = load_screening(db, screening_id, actor, lock=True)
        if screening.review_status == "draft":
            raise Conflict("Submit this screening before handing it over.")
        target = db.scalar(select(User).where(
            User.id == payload.assigned_counsellor_id, User.role == UserRole.COUNSELLOR,
            User.is_active.is_(True),
        ).with_for_update().execution_options(populate_existing=True))
        if target is None:
            raise InvalidOperation("Choose an active counsellor.")
        if screening.assigned_counsellor_id == target.id:
            raise Conflict("This case is already assigned to that counsellor.")
        db.add(CaseHandover(screening_id=screening.id,
            previous_counsellor_id=screening.assigned_counsellor_id,
            new_counsellor_id=target.id, actor_id=actor.id, reason=payload.reason))
        screening.assigned_counsellor_id = target.id
        db.execute(update(Followup).where(Followup.screening_id == screening.id,
            Followup.status == "scheduled").values(counsellor_id=target.id))
        audit(db, actor.id, "screening.handed_over", "screening", screening.id)
        db.flush()
        db.expire(screening,["assigned_counsellor"])
        response = screening_response(screening, actor)
    return response
