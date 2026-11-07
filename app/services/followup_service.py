"""Counsellor-owned appointment lifecycle, independent of screening review state."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.entities import Followup, Screening, utc_now
from app.schemas.followup import (
    FollowupCancel, FollowupComplete, FollowupCreate, FollowupRead, FollowupReschedule, FollowupStatus,
)
from app.schemas.user import UserRole
from app.services._common import audit, load_assigned_screening, require_actor, validate_page, write_operation
from app.services.errors import Conflict, NotFound


def _load(db: Session, followup_id: UUID, actor, *, lock: bool = False) -> Followup:
    # Lock the parent first, consistent with case assignment and review operations.
    item = db.scalar(select(Followup).where(Followup.id == followup_id))
    if item is None:
        raise NotFound("Follow-up not found.")
    try:
        load_assigned_screening(db, item.screening_id, actor, lock=lock)
    except NotFound:
        raise NotFound("Follow-up not found.") from None
    statement = select(Followup).where(Followup.id == followup_id)
    if lock:
        statement = statement.with_for_update()
    return db.scalar(statement.execution_options(populate_existing=True))


def create_followup(db: Session, payload: FollowupCreate, *, actor_id: UUID) -> FollowupRead:
    with write_operation(db):
        actor = require_actor(db, actor_id, {UserRole.COUNSELLOR})
        screening = load_assigned_screening(db, payload.screening_id, actor, lock=True)
        if screening.review_status not in {"in_review", "reviewed"}:
            raise Conflict("Begin review before scheduling a follow-up.")
        item = Followup(**payload.model_dump(), student_id=screening.student_id,
            counsellor_id=actor.id, status="scheduled")
        db.add(item)
        db.flush()
        audit(db, actor.id, "followup.scheduled", "followup", item.id)
        response = FollowupRead.model_validate(item)
    return response


def get_followup(db: Session, followup_id: UUID, *, actor_id: UUID) -> FollowupRead:
    actor = require_actor(db, actor_id, {UserRole.COUNSELLOR})
    return FollowupRead.model_validate(_load(db, followup_id, actor))


def list_followups(db: Session, *, actor_id: UUID, status: FollowupStatus | None = None,
                   due: bool = False, offset: int = 0, limit: int = 50) -> dict:
    actor = require_actor(db, actor_id, {UserRole.COUNSELLOR})
    validate_page(offset, limit)
    statement = select(Followup).join(Screening).where(
        Screening.assigned_counsellor_id == actor.id,
    )
    if status is not None:
        statement = statement.where(Followup.status == status)
    if due:
        statement = statement.where(Followup.status == "scheduled", Followup.scheduled_for <= utc_now())
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = db.scalars(statement.order_by(Followup.scheduled_for, Followup.id).offset(offset).limit(limit)).all()
    return {"items":[FollowupRead.model_validate(row) for row in rows], "total":total, "offset":offset, "limit":limit}


def reschedule_followup(db: Session, followup_id: UUID, payload: FollowupReschedule, *, actor_id: UUID) -> FollowupRead:
    with write_operation(db):
        actor = require_actor(db, actor_id, {UserRole.COUNSELLOR})
        item = _load(db, followup_id, actor, lock=True)
        if item.status != "scheduled":
            raise Conflict("Only scheduled appointments can be rescheduled.")
        item.scheduled_for = payload.scheduled_for
        item.reason = payload.reason
        audit(db, actor.id, "followup.rescheduled", "followup", item.id)
        db.flush()
        response = FollowupRead.model_validate(item)
    return response


def complete_followup(db: Session, followup_id: UUID, payload: FollowupComplete, *, actor_id: UUID) -> FollowupRead:
    with write_operation(db):
        actor = require_actor(db, actor_id, {UserRole.COUNSELLOR})
        item = _load(db, followup_id, actor, lock=True)
        if item.status == "completed" and item.outcome == payload.outcome:
            pass
        elif item.status != "scheduled":
            raise Conflict("Only scheduled appointments can be completed.")
        else:
            item.status = "completed"
            item.outcome = payload.outcome
            item.completed_at = utc_now()
            audit(db, actor.id, "followup.completed", "followup", item.id)
        db.flush()
        response = FollowupRead.model_validate(item)
    return response


def cancel_followup(db: Session, followup_id: UUID, payload: FollowupCancel, *, actor_id: UUID) -> FollowupRead:
    with write_operation(db):
        actor = require_actor(db, actor_id, {UserRole.COUNSELLOR})
        item = _load(db, followup_id, actor, lock=True)
        if item.status == "cancelled" and item.cancellation_reason == payload.reason:
            pass
        elif item.status != "scheduled":
            raise Conflict("Only scheduled appointments can be cancelled.")
        else:
            item.status = "cancelled"
            item.cancellation_reason = payload.reason
            item.cancelled_at = utc_now()
            audit(db, actor.id, "followup.cancelled", "followup", item.id)
        db.flush()
        response = FollowupRead.model_validate(item)
    return response
