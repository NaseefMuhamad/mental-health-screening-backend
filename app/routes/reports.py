from fastapi import APIRouter

from app.auth.permissions import CurrentUser, DatabaseSession
from app.schemas.report import OperationalSummary
from app.services import report_service


router = APIRouter(prefix="/reports", tags=["Operational reports"])


@router.get("/summary", response_model=OperationalSummary)
def summary(db: DatabaseSession, user: CurrentUser):
    return report_service.summary(db, actor_id=user.id)
