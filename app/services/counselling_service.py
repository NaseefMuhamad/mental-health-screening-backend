"""Append-only human review actions with restricted note access."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.entities import CounsellingRecord, Screening
from app.schemas.counselling import CounsellingCreate, CounsellingRead
from app.schemas.user import UserRole
from app.services._common import audit, load_screening, require_actor, validate_page, write_operation
from app.services.errors import Conflict


def create_record(db: Session, payload: CounsellingCreate, *, actor_id: UUID) -> CounsellingRead:
    with write_operation(db):
        actor = require_actor(db, actor_id, {UserRole.COUNSELLOR})
        screening = load_screening(db, payload.screening_id, actor, lock=True)
        if screening.review_status not in {"in_review", "reviewed"}:
            raise Conflict("Begin review before recording a counsellor action.")
        record = CounsellingRecord(**payload.model_dump(), reviewer_id=actor.id)
        db.add(record)
        screening.review_status = "reviewed"
        db.flush()
        audit(db, actor.id, "counselling.recorded", "counselling_record", record.id)
        response = CounsellingRead.model_validate(record)
    return response


def list_records(db: Session, *, actor_id: UUID, screening_id: UUID | None = None,
                 offset: int = 0, limit: int = 50) -> dict:
    actor = require_actor(db, actor_id, {UserRole.COUNSELLOR})
    validate_page(offset, limit)
    if screening_id is not None:
        load_screening(db, screening_id, actor)
    statement = select(CounsellingRecord).join(Screening).where(
        Screening.assigned_counsellor_id == actor.id, Screening.review_status != "draft",
    )
    if screening_id is not None:
        statement = statement.where(CounsellingRecord.screening_id == screening_id)
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = db.scalars(statement.order_by(CounsellingRecord.created_at.desc(), CounsellingRecord.id).offset(offset).limit(limit)).all()
    return {"items":[CounsellingRead.model_validate(row) for row in rows], "total":total, "offset":offset, "limit":limit}
