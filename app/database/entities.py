"""Persistent entities used by the first service step (one institution).

These definitions live in the existing database folder. They share the Base
already provided in base.py. No tables are created merely by importing them.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from app.database.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """Keep aware UTC datetimes, including in SQLite-based unit tests."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Timezone-aware datetime required.")
        return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class User(Base):
    """Staff identity. Authentication/invitation operations come in the auth step."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('administrator', 'screening_personnel', 'counsellor')",
            name="valid_user_role",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(320))
    email_key: Mapped[str] = mapped_column(String(320), unique=True)
    role: Mapped[str] = mapped_column(String(32))
    # A new identity is inactive until the controlled auth step activates it.
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    password_hash: Mapped[str | None] = mapped_column(String(512), default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)


class Student(Base):
    __tablename__ = "students"
    __table_args__ = (
        CheckConstraint("age >= 1 AND age <= 120", name="valid_student_age"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    student_code: Mapped[str] = mapped_column(String(50))
    student_code_key: Mapped[str] = mapped_column(String(150), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    age: Mapped[int]
    department: Mapped[str] = mapped_column(String(120))
    academic_year: Mapped[str] = mapped_column(String(32))
    institution: Mapped[str] = mapped_column(String(120))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)


class Screening(Base):
    __tablename__ = "screenings"
    __table_args__ = (
        CheckConstraint(
            "review_status IN ('draft', 'awaiting_review', 'in_review', 'reviewed')",
            name="valid_review_status",
        ),
        CheckConstraint(
            "prediction_status IN ('unavailable', 'processing', 'available', 'failed')",
            name="valid_prediction_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    student_id: Mapped[UUID] = mapped_column(ForeignKey("students.id", ondelete="RESTRICT"), index=True)
    measured_at: Mapped[datetime] = mapped_column(UTCDateTime())
    recorded_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    assigned_counsellor_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True, default=None
    )
    student: Mapped[Student] = relationship(Student, foreign_keys=[student_id], lazy="selectin")

    @property
    def student_name(self):
        return self.student.name

    @property
    def student_code(self):
        return self.student.student_code

    assigned_counsellor: Mapped[User | None] = relationship(User, foreign_keys=[assigned_counsellor_id], lazy="selectin")

    @property
    def assigned_counsellor_name(self):
        return self.assigned_counsellor.name if self.assigned_counsellor else None

    review_status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    prediction_status: Mapped[str] = mapped_column(String(32), default="unavailable")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    submitted_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), default=None)
    measurements: Mapped[Measurement] = relationship(
        back_populates="screening", uselist=False, cascade="all, delete-orphan"
    )


class Measurement(Base):
    __tablename__ = "measurements"
    __table_args__ = (
        CheckConstraint("heart_rate_bpm > 0", name="positive_heart_rate"),
        CheckConstraint(
            "(systolic_mmhg IS NULL AND diastolic_mmhg IS NULL) OR "
            "(systolic_mmhg IS NOT NULL AND diastolic_mmhg IS NOT NULL "
            "AND diastolic_mmhg > 0 AND systolic_mmhg > diastolic_mmhg)",
            name="paired_blood_pressure",
        ),
        CheckConstraint("pupil_diameter_mm IS NULL OR pupil_diameter_mm > 0", name="positive_pupil_size"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    screening_id: Mapped[UUID] = mapped_column(
        ForeignKey("screenings.id", ondelete="RESTRICT"), unique=True
    )
    heart_rate_bpm: Mapped[float] = mapped_column(Float)
    systolic_mmhg: Mapped[float | None] = mapped_column(Float, default=None)
    diastolic_mmhg: Mapped[float | None] = mapped_column(Float, default=None)
    pupil_diameter_mm: Mapped[float | None] = mapped_column(Float, default=None)
    recorded_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    screening: Mapped[Screening] = relationship(back_populates="measurements")


class AuditEvent(Base):
    """Operational events only; no measurement values, notes, tokens or passwords."""

    __tablename__ = "audit_events"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    action: Mapped[str] = mapped_column(String(80))
    resource_type: Mapped[str] = mapped_column(String(40))
    resource_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), default=None)


class Invitation(Base):
    __tablename__ = "invitations"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    email: Mapped[str] = mapped_column(String(320))
    role: Mapped[str] = mapped_column(String(32))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    invited_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    accepted_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), default=None)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), default=None)


class ControlLock(Base):
    """Serialize staff-management operations, including the last-admin rule."""

    __tablename__ = "control_locks"
    name: Mapped[str] = mapped_column(String(80), primary_key=True)


class LoginBucket(Base):
    """Database-backed attempt windows, shared by API workers."""

    __tablename__ = "login_buckets"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)


class StaffChange(Base):
    __tablename__ = "staff_changes"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    action: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)


class CounsellingRecord(Base):
    __tablename__ = "counselling_records"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    screening_id: Mapped[UUID] = mapped_column(ForeignKey("screenings.id", ondelete="RESTRICT"), index=True)
    reviewer_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    action: Mapped[str] = mapped_column(String(60))
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime())
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)


    screening: Mapped[Screening] = relationship(Screening, foreign_keys=[screening_id], lazy="selectin")

    @property
    def student_name(self):
        return self.screening.student_name

    @property
    def student_code(self):
        return self.screening.student_code


class Followup(Base):
    __tablename__ = "followups"
    __table_args__ = (
        CheckConstraint("status IN ('scheduled', 'completed', 'cancelled')", name="valid_followup_status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    screening_id: Mapped[UUID] = mapped_column(ForeignKey("screenings.id", ondelete="RESTRICT"), index=True)
    student_id: Mapped[UUID] = mapped_column(ForeignKey("students.id", ondelete="RESTRICT"), index=True)
    counsellor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    scheduled_for: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    reason: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), default="scheduled")
    outcome: Mapped[str | None] = mapped_column(Text, default=None)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, default=None)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), default=None)
    cancelled_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)


    student: Mapped[Student] = relationship(Student, foreign_keys=[student_id], lazy="selectin")

    @property
    def student_name(self):
        return self.student.name

    @property
    def student_code(self):
        return self.student.student_code


class CaseHandover(Base):
    """Preserve who transferred a case, to whom, when and why."""

    __tablename__ = "case_handovers"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    screening_id: Mapped[UUID] = mapped_column(ForeignKey("screenings.id", ondelete="RESTRICT"), index=True)
    previous_counsellor_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    new_counsellor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)


class ScreeningAssessment(Base):
    """Append-only contextual input snapshots collected by the assigned counsellor."""
    __tablename__ = "screening_assessments"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    screening_id: Mapped[UUID] = mapped_column(ForeignKey("screenings.id", ondelete="RESTRICT"), index=True)
    recorded_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    inputs_json: Mapped[str] = mapped_column(Text)
    protocol: Mapped[str] = mapped_column(String(80), default="demo_dataset_scales_v1")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)


class ScreeningPrediction(Base):
    """Separate stress/anxiety outputs linked to the exact assessment snapshot."""
    __tablename__ = "screening_predictions"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    screening_id: Mapped[UUID] = mapped_column(ForeignKey("screenings.id", ondelete="RESTRICT"), index=True)
    assessment_id: Mapped[UUID] = mapped_column(ForeignKey("screening_assessments.id", ondelete="RESTRICT"), index=True)
    requested_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    stress_level: Mapped[str] = mapped_column(String(10))
    anxiety_level: Mapped[str] = mapped_column(String(10))
    model_version: Mapped[str] = mapped_column(String(120))
    model_details_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
