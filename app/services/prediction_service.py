"""Explicit unavailable-model behavior. No trained model or fabricated output."""

from uuid import UUID

from sqlalchemy.orm import Session

from app.schemas.prediction import PredictionRead, PredictionStatus
from app.schemas.user import UserRole
from app.services._common import load_screening, require_actor
from app.services.errors import DependencyUnavailable


def get_prediction(db: Session, screening_id: UUID, *, actor_id: UUID) -> PredictionRead:
    """Only the assigned counsellor can read clinical screening indications.

    Other staff can see prediction_status in their permitted session responses.
    No prediction table or model file is introduced while dataset confirmation
    and the validated ML contract are pending.
    """
    actor = require_actor(db, actor_id, {UserRole.COUNSELLOR})
    screening = load_screening(db, screening_id, actor)
    if screening.prediction_status != PredictionStatus.UNAVAILABLE:
        raise DependencyUnavailable("Prediction retrieval is not configured for the current model status.")
    return PredictionRead(
        screening_id=screening.id, status=PredictionStatus.UNAVAILABLE,
        message="Model not connected.",
    )


def request_prediction(db: Session, screening_id: UUID, *, actor_id: UUID) -> PredictionRead:
    """A request returns the unavailable state without guessing results or writing data."""
    return get_prediction(db, screening_id, actor_id=actor_id)
