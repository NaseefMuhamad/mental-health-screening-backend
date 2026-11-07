"""Screening personnel collect demo answers; assigned counsellors verify snapshots."""
import json
from uuid import UUID
from sqlalchemy import select
from app.database.entities import ScreeningAssessment,Student
from app.schemas.assessment import AssessmentRead
from app.schemas.user import UserRole
from app.services._common import require_actor,load_screening,load_assigned_screening,write_operation,audit
from app.services.errors import Conflict

def as_response(item):
    return AssessmentRead(id=item.id,screening_id=item.screening_id,recorded_by=item.recorded_by,inputs=json.loads(item.inputs_json),protocol=item.protocol,created_at=item.created_at)

def latest(db,screening_id):
    return db.scalar(select(ScreeningAssessment).where(ScreeningAssessment.screening_id==screening_id).order_by(ScreeningAssessment.created_at.desc(),ScreeningAssessment.id.desc()).limit(1))

def append_snapshot(db,screening,actor,payload):
    student=db.get(Student,screening.student_id)
    inputs={'Sleep_Hours':payload.sleep_hours,'Screen_Time':payload.screen_time,'Assignment_Load':payload.assignment_load,'Exam_Pressure':payload.exam_pressure,'Social_Support':payload.social_support,'Heart_Rate':screening.measurements.heart_rate_bpm,'Department':student.department,'Academic_Year':student.academic_year}
    item=ScreeningAssessment(screening_id=screening.id,recorded_by=actor.id,inputs_json=json.dumps(inputs,allow_nan=False),protocol=payload.protocol)
    db.add(item);db.flush();screening.prediction_status='unavailable'
    audit(db,actor.id,'assessment.recorded','screening_assessment',item.id)
    return item

def get_latest(db,screening_id:UUID,*,actor_id:UUID):
    actor=require_actor(db,actor_id,{UserRole.COUNSELLOR,UserRole.SCREENING_PERSONNEL})
    if actor.role==UserRole.COUNSELLOR:load_assigned_screening(db,screening_id,actor)
    else:load_screening(db,screening_id,actor)
    item=latest(db,screening_id)
    return as_response(item) if item else None

def create(db,screening_id,payload,*,actor_id):
    with write_operation(db):
        actor=require_actor(db,actor_id,{UserRole.SCREENING_PERSONNEL});s=load_screening(db,screening_id,actor,lock=True)
        if s.review_status!='draft':raise Conflict('Submitted screening answers are preserved. Create a new screening to record a new assessment.')
        item=append_snapshot(db,s,actor,payload);response=as_response(item)
    return response
