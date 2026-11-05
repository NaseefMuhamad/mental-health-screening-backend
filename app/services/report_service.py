"""Operational counts within a staff member's record scope; no clinical claims."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.entities import Followup, Screening, utc_now
from app.schemas.report import OperationalSummary
from app.schemas.user import UserRole
from app.services._common import require_actor, screening_visibility


def summary(db: Session, *, actor_id: UUID) -> OperationalSummary:
    actor = require_actor(db, actor_id, set(UserRole))
    visible = screening_visibility(actor)
    grouped = db.execute(select(Screening.review_status, func.count()).where(visible).group_by(Screening.review_status)).all()
    counts = dict(grouped)
    followups = select(Followup.status, func.count()).join(Screening).where(visible)
    followup_counts = dict(db.execute(followups.group_by(Followup.status)).all())
    scope = {UserRole.ADMINISTRATOR:"institution", UserRole.SCREENING_PERSONNEL:"own_screenings", UserRole.COUNSELLOR:"assigned_cases"}[UserRole(actor.role)]
    return OperationalSummary(scope=scope, generated_at=utc_now(), screening_sessions=sum(counts.values()),
        draft=counts.get("draft",0), awaiting_review=counts.get("awaiting_review",0),
        in_review=counts.get("in_review",0), reviewed=counts.get("reviewed",0),
        scheduled_followups=followup_counts.get("scheduled",0), completed_followups=followup_counts.get("completed",0))
