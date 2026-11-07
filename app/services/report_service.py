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
    if actor.role == UserRole.COUNSELLOR:
        followups = followups.where(Screening.assigned_counsellor_id == actor.id)
    followup_counts = dict(db.execute(followups.group_by(Followup.status)).all())
    scope = {UserRole.ADMINISTRATOR:"institution", UserRole.SCREENING_PERSONNEL:"own_screenings", UserRole.COUNSELLOR:"submitted_screenings"}[UserRole(actor.role)]
    return OperationalSummary(scope=scope, generated_at=utc_now(), screening_sessions=sum(counts.values()),
        draft=counts.get("draft",0), awaiting_review=counts.get("awaiting_review",0),
        in_review=counts.get("in_review",0), reviewed=counts.get("reviewed",0),
        scheduled_followups=followup_counts.get("scheduled",0), completed_followups=followup_counts.get("completed",0))


def counsellor_queue(db: Session, *, actor_id: UUID, assigned_only: bool = False, offset: int = 0, limit: int = 20) -> dict:
    """Paged submitted-case queue with latest-input predictions and no private notes."""
    from sqlalchemy import select
    from app.database.entities import ScreeningAssessment, ScreeningPrediction, Student
    from app.schemas.report import CounsellorQueueItem
    from app.services._common import validate_page

    actor = require_actor(db, actor_id, {UserRole.COUNSELLOR})
    validate_page(offset, limit)
    filters = [Screening.review_status != "draft"]
    if assigned_only:
        filters.append(Screening.assigned_counsellor_id == actor.id)
    total = db.scalar(select(func.count()).select_from(Screening).where(*filters)) or 0
    assessments = select(
        ScreeningAssessment.id.label("assessment_id"), ScreeningAssessment.screening_id,
        func.row_number().over(partition_by=ScreeningAssessment.screening_id,
            order_by=(ScreeningAssessment.created_at.desc(), ScreeningAssessment.id.desc())).label("position"),
    ).subquery()
    predictions = select(
        ScreeningPrediction.id.label("prediction_id"), ScreeningPrediction.assessment_id,
        func.row_number().over(partition_by=ScreeningPrediction.assessment_id,
            order_by=(ScreeningPrediction.created_at.desc(), ScreeningPrediction.id.desc())).label("position"),
    ).subquery()
    query = select(Screening, Student, assessments.c.assessment_id, ScreeningPrediction).join(
        Student, Student.id == Screening.student_id,
    ).outerjoin(assessments, (assessments.c.screening_id == Screening.id) & (assessments.c.position == 1)).outerjoin(
        predictions, (predictions.c.assessment_id == assessments.c.assessment_id) & (predictions.c.position == 1),
    ).outerjoin(ScreeningPrediction, ScreeningPrediction.id == predictions.c.prediction_id).where(*filters).order_by(
        Screening.submitted_at.desc(), Screening.created_at.desc(), Screening.id,
    ).offset(offset).limit(limit)
    items = []
    for screening, student, assessment_id, prediction in db.execute(query):
        items.append(CounsellorQueueItem(
            id=screening.id, student_id=student.id, student_code=student.student_code,
            student_name=student.name, measured_at=screening.measured_at,
            review_status=screening.review_status, assigned_counsellor_id=screening.assigned_counsellor_id, assigned_counsellor_name=screening.assigned_counsellor_name,
            assigned_to_me=screening.assigned_counsellor_id == actor.id, prediction_status=screening.prediction_status, assessment_complete=assessment_id is not None,
            stress_level=prediction.stress_level if prediction else None,
            anxiety_level=prediction.anxiety_level if prediction else None,
            model_version=prediction.model_version if prediction else None,
            generated_at=prediction.created_at if prediction else None,
        ))
    return {"items":items, "total":total, "offset":offset, "limit":limit}


def screening_activity(db: Session, *, actor_id: UUID):
    """Seven aggregated UTC days; never download full screening histories for a chart."""
    from datetime import timedelta
    from app.schemas.report import ScreeningActivity, ActivityDay
    actor=require_actor(db,actor_id,set(UserRole))
    today=utc_now().replace(hour=0,minute=0,second=0,microsecond=0)
    start=today-timedelta(days=6)
    day=func.date(Screening.created_at)
    rows=db.execute(select(day,func.count()).where(screening_visibility(actor),
        Screening.created_at>=start,Screening.created_at<today+timedelta(days=1)).group_by(day)).all()
    counts={str(key):count for key,count in rows}
    return ScreeningActivity(items=[ActivityDay(day=(start+timedelta(days=i)).date().isoformat(),
        screenings=counts.get((start+timedelta(days=i)).date().isoformat(),0)) for i in range(7)])
