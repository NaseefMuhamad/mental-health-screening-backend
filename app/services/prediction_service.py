import json
from sqlalchemy import select
from app.database.entities import ScreeningPrediction
from app.schemas.prediction import PredictionRead,PredictionStatus
from app.schemas.user import UserRole
from app.services._common import require_actor,load_screening,load_assigned_screening,write_operation,audit
from app.services.assessment_service import latest
from app.services.errors import Conflict,DependencyUnavailable,InvalidOperation
from app.services import ml_client

def response(s,item=None):
    if item is None:return PredictionRead(screening_id=s.id,status=PredictionStatus.FAILED if s.prediction_status=='failed' else PredictionStatus.UNAVAILABLE,message='Prediction pending. Screening answers are saved; retry inference when the ML service is running.')
    return PredictionRead(screening_id=s.id,status=PredictionStatus.AVAILABLE,assessment_id=item.assessment_id,stress_level=item.stress_level,anxiety_level=item.anxiety_level,model_version=item.model_version,generated_at=item.created_at,message='Demo estimates from simulated dataset categories; not diagnoses.')

def prediction_for(db,s,assessment):
    if assessment is None:return None
    return db.scalar(select(ScreeningPrediction).where(ScreeningPrediction.screening_id==s.id,ScreeningPrediction.assessment_id==assessment.id).order_by(ScreeningPrediction.created_at.desc(),ScreeningPrediction.id.desc()).limit(1))

def get_prediction(db,screening_id,*,actor_id):
    actor=require_actor(db,actor_id,{UserRole.COUNSELLOR});s=load_screening(db,screening_id,actor)
    return response(s,prediction_for(db,s,latest(db,s.id)))

def _generate(db,screening_id,*,actor_id,from_screening=False):
    with write_operation(db):
        actor=require_actor(db,actor_id,{UserRole.SCREENING_PERSONNEL} if from_screening else {UserRole.COUNSELLOR})
        s=load_screening(db,screening_id,actor,lock=True) if from_screening else load_assigned_screening(db,screening_id,actor,lock=True)
        if s.review_status=='draft':raise Conflict('Submit the screening before generating predictions.')
        assessment=latest(db,s.id)
        if assessment is None:raise Conflict('Save the contextual assessment before requesting predictions.')
        existing=prediction_for(db,s,assessment)
        if existing:return response(s,existing)
        result=ml_client.predict(json.loads(assessment.inputs_json))
        item=ScreeningPrediction(screening_id=s.id,assessment_id=assessment.id,requested_by=actor.id,stress_level=result['stress']['level'],anxiety_level=result['anxiety']['level'],model_version=result['model_version'],model_details_json=json.dumps(result,allow_nan=False))
        db.add(item);db.flush();s.prediction_status='available'
        audit(db,actor.id,'prediction.generated','screening_prediction',item.id)
        value=response(s,item)
    return value


def request_prediction(db,screening_id,*,actor_id):
    """Assigned counsellor can retry a failed service call, not enter screening answers."""
    return _generate(db,screening_id,actor_id=actor_id)

def generate_after_submission(db,screening_id,*,actor_id):
    """Submission remains saved and visible even if local inference is unavailable."""
    try:
        _generate(db,screening_id,actor_id=actor_id,from_screening=True)
    except (DependencyUnavailable,InvalidOperation):
        with write_operation(db):
            actor=require_actor(db,actor_id,{UserRole.SCREENING_PERSONNEL})
            s=load_screening(db,screening_id,actor,lock=True)
            # A concurrent successful retry must not be replaced by a failure marker.
            if prediction_for(db,s,latest(db,s.id)) is None:
                s.prediction_status='failed'
                audit(db,actor.id,'prediction.pending_retry','screening',s.id)
