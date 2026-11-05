"""Shared identity, visibility, transaction and audit rules for services."""

from contextlib import contextmanager
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.entities import AuditEvent, Screening, User
from app.schemas.user import UserRole
from app.services.errors import (
    AuthenticationRequired, Conflict, InvalidOperation, NotFound, PermissionDenied,
)


def require_actor(db: Session, actor_id: UUID, roles: set[UserRole]) -> User:
    """Reload identity from the database; never accept a role from request data.

    actor_id must come from the authentication dependency, not a URL/body/query.
    This function checks identity/activation but does not authenticate a token.
    """
    actor = db.scalar(select(User).where(User.id == actor_id).execution_options(populate_existing=True))
    if actor is None or not actor.is_active:
        raise AuthenticationRequired("An active staff account is required.")
    if actor.role not in roles:
        raise PermissionDenied("Your role cannot perform this operation.")
    return actor


def validate_page(offset: int, limit: int) -> None:
    if type(offset) is not int or type(limit) is not int or offset < 0 or not 1 <= limit <= 100:
        raise InvalidOperation("Use offset >= 0 and limit between 1 and 100.")


def screening_visibility(actor: User):
    """Admin: all; screening staff: own; counsellor: assigned, submitted cases."""
    if actor.role == UserRole.ADMINISTRATOR:
        return Screening.id.is_not(None)
    if actor.role == UserRole.SCREENING_PERSONNEL:
        return Screening.recorded_by == actor.id
    return (Screening.assigned_counsellor_id == actor.id) & (Screening.review_status != "draft")


def load_screening(db: Session, screening_id: UUID, actor: User, *, lock: bool = False) -> Screening:
    statement = select(Screening).where(Screening.id == screening_id, screening_visibility(actor))
    if lock:
        statement = statement.with_for_update()
    screening = db.scalar(statement.execution_options(populate_existing=True))
    if screening is None:
        # Use the same response for a missing case and a case outside this user's scope.
        raise NotFound("Screening not found.")
    return screening


def audit(db: Session, actor_id: UUID, action: str, resource_type: str, resource_id: UUID) -> None:
    db.add(AuditEvent(actor_id=actor_id, action=action, resource_type=resource_type, resource_id=resource_id))


@contextmanager
def write_operation(db: Session):
    """A write service owns one transaction, including any audit event.

    Callers must not have unrelated pending writes in this request Session.
    Do not wrap these functions in session_scope or another auto-commit wrapper.
    """
    try:
        yield
        db.commit()
    except IntegrityError:
        db.rollback()
        raise Conflict("The change conflicts with an existing record or database constraint.") from None
    except BaseException:
        db.rollback()
        raise
