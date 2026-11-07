from fastapi import APIRouter

from app.auth.permissions import CurrentUser, DatabaseSession
from app.schemas.report import OperationalSummary
from app.services import report_service


router = APIRouter(prefix="/reports", tags=["Operational reports"])


@router.get("/summary", response_model=OperationalSummary)
def summary(db: DatabaseSession, user: CurrentUser):
    return report_service.summary(db, actor_id=user.id)


from fastapi import Query
from app.auth.permissions import CounsellorUser
from app.schemas._common import Page
from app.schemas.report import CounsellorQueueItem

@router.get("/counsellor-queue", response_model=Page[CounsellorQueueItem])
def counsellor_queue(db: DatabaseSession, user: CounsellorUser, assigned_only: bool = False,
                    offset: int = Query(0,ge=0), limit: int = Query(20,ge=1,le=100)):
    return report_service.counsellor_queue(db,actor_id=user.id,assigned_only=assigned_only,offset=offset,limit=limit)


from app.schemas.report import ScreeningActivity

@router.get("/activity", response_model=ScreeningActivity)
def screening_activity(db: DatabaseSession, user: CurrentUser):
    return report_service.screening_activity(db,actor_id=user.id)
