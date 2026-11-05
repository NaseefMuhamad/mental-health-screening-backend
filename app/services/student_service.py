"""Student registration and access-controlled directory/profile operations."""

from uuid import UUID

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from app.database.entities import Screening, Student
from app.schemas.student import StudentCreate, StudentRead, StudentUpdate
from app.schemas.user import UserRole
from app.services._common import audit, require_actor, validate_page, write_operation
from app.services.errors import Conflict, InvalidOperation, NotFound


READ_ROLES = set(UserRole)
WRITE_ROLES = {UserRole.ADMINISTRATOR, UserRole.SCREENING_PERSONNEL}


def _visible_students(actor):
    if actor.role != UserRole.COUNSELLOR:
        return Student.id.is_not(None)
    return exists().where(
        Screening.student_id == Student.id,
        Screening.assigned_counsellor_id == actor.id,
        Screening.review_status != "draft",
    )


def create_student(db: Session, payload: StudentCreate, *, actor_id: UUID) -> StudentRead:
    with write_operation(db):
        actor = require_actor(db, actor_id, WRITE_ROLES)
        key = payload.student_code.casefold()
        if db.scalar(select(Student.id).where(Student.student_code_key == key)):
            raise Conflict("That student code is already registered.")
        student = Student(**payload.model_dump(), student_code_key=key, created_by=actor.id)
        db.add(student)
        db.flush()
        response = StudentRead.model_validate(student)
        audit(db, actor.id, "student.created", "student", student.id)
    return response


def get_student(db: Session, student_id: UUID, *, actor_id: UUID) -> StudentRead:
    actor = require_actor(db, actor_id, READ_ROLES)
    student = db.scalar(select(Student).where(Student.id == student_id, _visible_students(actor)))
    if student is None:
        raise NotFound("Student not found.")
    return StudentRead.model_validate(student)


def list_students(
    db: Session, *, actor_id: UUID, search: str = "", offset: int = 0, limit: int = 50,
) -> dict:
    actor = require_actor(db, actor_id, READ_ROLES)
    validate_page(offset, limit)
    if not isinstance(search, str) or len(search) > 120:
        raise InvalidOperation("Search must be text of at most 120 characters.")
    statement = select(Student).where(_visible_students(actor))
    term = search.strip()
    if term:
        statement = statement.where(or_(
            Student.name.icontains(term, autoescape=True),
            Student.student_code.icontains(term, autoescape=True),
        ))
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    students = db.scalars(statement.order_by(Student.created_at.desc(), Student.id).offset(offset).limit(limit)).all()
    return {"items": [StudentRead.model_validate(item) for item in students], "total": total, "offset": offset, "limit": limit}


def update_student(
    db: Session, student_id: UUID, payload: StudentUpdate, *, actor_id: UUID,
) -> StudentRead:
    with write_operation(db):
        actor = require_actor(db, actor_id, WRITE_ROLES)
        student = db.scalar(select(Student).where(Student.id == student_id).with_for_update())
        if student is None:
            raise NotFound("Student not found.")
        for field, value in payload.model_dump().items():
            setattr(student, field, value)
        db.flush()
        response = StudentRead.model_validate(student)
        audit(db, actor.id, "student.updated", "student", student.id)
    return response
