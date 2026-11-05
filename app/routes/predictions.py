from uuid import UUID

from fastapi import APIRouter

from app.auth.permissions import CounsellorUser, DatabaseSession
from app.schemas.prediction import PredictionRead, PredictionRequest
from app.services import prediction_service


router = APIRouter(prefix="/predictions", tags=["Predictions (model unavailable)"])


@router.post("", response_model=PredictionRead)
def request_prediction(payload: PredictionRequest, db: DatabaseSession, user: CounsellorUser):
    return prediction_service.request_prediction(db, payload.screening_id, actor_id=user.id)


@router.get("/{screening_id}", response_model=PredictionRead)
def get_prediction(screening_id: UUID, db: DatabaseSession, user: CounsellorUser):
    return prediction_service.get_prediction(db, screening_id, actor_id=user.id)
