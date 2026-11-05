"""Controlled staff onboarding, persistent sessions and immediate revocation."""

from datetime import timedelta
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.auth.config import get_settings
from app.auth.security import hash_password, hash_token, new_token, verify_password
from app.database.entities import (
    AuthSession, ControlLock, Followup, Invitation, LoginBucket, Screening, StaffChange, User, utc_now,
)
from app.schemas.user import (
    BootstrapAdmin, InvitationAccept, InvitationIssued, InvitationRead, LoginRequest,
    LoginResponse, UserInviteCreate, UserRead, UserRole, UserRoleUpdate, UserStatusUpdate,
)
from app.services._common import audit, require_actor, validate_page, write_operation
from app.services.errors import AuthenticationRequired, Conflict, InvalidOperation, NotFound, RateLimited


def _insert_missing(db: Session, table, values: dict, key: str) -> None:
    dialect = db.get_bind().dialect.name
    insert = pg_insert if dialect == "postgresql" else sqlite_insert if dialect == "sqlite" else None
    if insert is None:
        raise RuntimeError("This backend supports PostgreSQL; SQLite is used only in tests.")
    db.execute(insert(table).values(**values).on_conflict_do_nothing(index_elements=[key]))


def _staff_lock(db: Session) -> None:
    _insert_missing(db, ControlLock.__table__, {"name": "staff-management"}, "name")
    db.scalar(select(ControlLock).where(ControlLock.name == "staff-management").with_for_update())


def _revoke_sessions(db: Session, user_id: UUID) -> None:
    db.execute(update(AuthSession).where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None)).values(revoked_at=utc_now()))


def bootstrap_admin(db: Session, payload: BootstrapAdmin) -> UserRead:
    with write_operation(db):
        _staff_lock(db)
        if db.scalar(select(User.id).where(User.role == UserRole.ADMINISTRATOR).limit(1)):
            raise Conflict("An administrator already exists. Bootstrap cannot run again.")
        key = str(payload.email).casefold()
        if db.scalar(select(User.id).where(User.email_key == key)):
            raise Conflict("That email is already registered.")
        user = User(name=payload.name, email=str(payload.email), email_key=key,
            role=UserRole.ADMINISTRATOR.value, is_active=True,
            password_hash=hash_password(payload.password.get_secret_value()))
        db.add(user)
        db.flush()
        audit(db, user.id, "administrator.bootstrapped", "user", user.id)
        response = UserRead.model_validate(user)
    return response


def issue_invitation(db: Session, payload: UserInviteCreate, *, actor_id: UUID) -> InvitationIssued:
    raw_token = new_token()
    with write_operation(db):
        _staff_lock(db)
        actor = require_actor(db, actor_id, {UserRole.ADMINISTRATOR})
        key = str(payload.email).casefold()
        user = db.scalar(select(User).where(User.email_key == key).with_for_update())
        if user is not None and (user.password_hash is not None or user.is_active):
            raise Conflict("That staff account already exists. Manage its status instead.")
        if user is None:
            user = User(name=payload.name, email=str(payload.email), email_key=key,
                role=payload.role.value, is_active=False)
            db.add(user)
            db.flush()
        else:
            user.name = payload.name
            user.role = payload.role.value
            db.execute(update(Invitation).where(Invitation.user_id == user.id,
                Invitation.accepted_at.is_(None), Invitation.revoked_at.is_(None)).values(revoked_at=utc_now()))
        invitation = Invitation(user_id=user.id, email=str(payload.email), role=payload.role.value,
            invited_by=actor.id, token_hash=hash_token(raw_token),
            expires_at=utc_now() + timedelta(hours=get_settings().invitation_hours))
        db.add(invitation)
        db.flush()
        audit(db, actor.id, "staff.invited", "user", user.id)
        response = InvitationIssued(invitation=InvitationRead.model_validate(invitation), acceptance_token=raw_token)
    return response


def revoke_invitation(db: Session, invitation_id: UUID, *, actor_id: UUID) -> None:
    with write_operation(db):
        _staff_lock(db)
        actor = require_actor(db, actor_id, {UserRole.ADMINISTRATOR})
        invitation = db.scalar(select(Invitation).where(Invitation.id == invitation_id).with_for_update())
        if invitation is None:
            raise NotFound("Invitation not found.")
        if invitation.accepted_at is not None:
            raise Conflict("This invitation was already accepted. Manage the staff account instead.")
        if invitation.revoked_at is None:
            invitation.revoked_at = utc_now()
            audit(db, actor.id, "staff.invitation_revoked", "user", invitation.user_id)


def accept_invitation(db: Session, payload: InvitationAccept) -> UserRead:
    with write_operation(db):
        _staff_lock(db)
        invitation = db.scalar(select(Invitation).where(
            Invitation.token_hash == hash_token(payload.token.get_secret_value())
        ).with_for_update())
        if invitation is None or invitation.accepted_at is not None or invitation.revoked_at is not None or invitation.expires_at <= utc_now():
            raise InvalidOperation("Invitation is invalid, expired or already used.")
        user = db.scalar(select(User).where(User.id == invitation.user_id).with_for_update())
        if user is None or user.is_active or user.password_hash is not None:
            raise InvalidOperation("Invitation is invalid, expired or already used.")
        user.password_hash = hash_password(payload.password.get_secret_value())
        user.is_active = True
        user.role = invitation.role
        invitation.accepted_at = utc_now()
        db.flush()
        audit(db, user.id, "staff.invitation_accepted", "user", user.id)
        response = UserRead.model_validate(user)
    return response


def _login_budget(db: Session, email: str, client_ip: str) -> LoginBucket:
    now = utc_now()
    expiry = now + timedelta(minutes=15)
    buckets = sorted([(hash_token(f"email:{email}"), 10), (hash_token(f"ip:{client_ip}"), 120)])
    email_bucket = None
    for key, limit in buckets:
        _insert_missing(db, LoginBucket.__table__, {"key":key, "attempts":0, "expires_at":expiry}, "key")
        bucket = db.scalar(select(LoginBucket).where(LoginBucket.key == key).with_for_update().execution_options(populate_existing=True))
        if bucket.expires_at <= now:
            bucket.attempts = 0
            bucket.expires_at = expiry
        if bucket.attempts >= limit:
            retry = max(1, int((bucket.expires_at - now).total_seconds()) + 1)
            raise RateLimited("Too many sign-in attempts. Try again later.", retry)
        bucket.attempts += 1
        if key == hash_token(f"email:{email}"):
            email_bucket = bucket
    return email_bucket


def login(db: Session, payload: LoginRequest, *, client_ip: str) -> LoginResponse:
    response = None
    with write_operation(db):
        email_bucket = _login_budget(db, str(payload.email).casefold(), client_ip)
        user = db.scalar(select(User).where(User.email_key == str(payload.email).casefold()).with_for_update())
        valid = verify_password(payload.password.get_secret_value(), user.password_hash if user else None)
        if user is not None and user.is_active and valid:
            raw_token = new_token()
            session = AuthSession(user_id=user.id, token_hash=hash_token(raw_token),
                expires_at=utc_now() + timedelta(minutes=get_settings().session_minutes))
            db.add(session)
            email_bucket.attempts = 0
            db.flush()
            audit(db, user.id, "session.created", "auth_session", session.id)
            response = LoginResponse(access_token=raw_token, user=UserRead.model_validate(user))
    # Failed attempts must commit their counters before returning the generic error.
    if response is None:
        raise AuthenticationRequired("Invalid email or password.")
    return response


def logout(db: Session, session_id: UUID, *, actor_id: UUID) -> None:
    with write_operation(db):
        session = db.scalar(select(AuthSession).where(AuthSession.id == session_id, AuthSession.user_id == actor_id).with_for_update())
        if session is not None and session.revoked_at is None:
            session.revoked_at = utc_now()
            audit(db, actor_id, "session.revoked", "auth_session", session.id)


def list_users(db: Session, *, actor_id: UUID, offset: int = 0, limit: int = 50) -> dict:
    require_actor(db, actor_id, {UserRole.ADMINISTRATOR})
    validate_page(offset, limit)
    total = db.scalar(select(func.count()).select_from(User)) or 0
    rows = db.scalars(select(User).order_by(User.created_at.desc(), User.id).offset(offset).limit(limit)).all()
    return {"items":[UserRead.model_validate(row) for row in rows], "total":total, "offset":offset, "limit":limit}


def _protect_assignments(db: Session, user: User) -> None:
    if user.role != UserRole.COUNSELLOR:
        return
    pending_case = db.scalar(select(Screening.id).where(Screening.assigned_counsellor_id == user.id, Screening.review_status != "reviewed").limit(1))
    pending_followup = db.scalar(select(Followup.id).where(Followup.counsellor_id == user.id, Followup.status == "scheduled").limit(1))
    if pending_case or pending_followup:
        raise Conflict("Resolve or reassign outstanding cases and follow-ups before changing this counsellor's access.")


def _protect_last_admin(db: Session, user: User) -> None:
    if user.role == UserRole.ADMINISTRATOR and user.is_active:
        others = db.scalar(select(func.count()).select_from(User).where(
            User.role == UserRole.ADMINISTRATOR, User.is_active.is_(True), User.id != user.id,
        )) or 0
        if not others:
            raise Conflict("The last active administrator cannot be deactivated or demoted.")


def update_status(db: Session, user_id: UUID, payload: UserStatusUpdate, *, actor_id: UUID) -> UserRead:
    with write_operation(db):
        _staff_lock(db)
        actor = require_actor(db, actor_id, {UserRole.ADMINISTRATOR})
        user = db.scalar(select(User).where(User.id == user_id).with_for_update())
        if user is None:
            raise NotFound("Staff account not found.")
        if user.is_active != payload.is_active:
            if not payload.is_active:
                _protect_last_admin(db, user)
            elif user.password_hash is None:
                raise Conflict("This staff member must accept an invitation and set a password first.")
            user.is_active = payload.is_active
            _revoke_sessions(db, user.id)
            db.add(StaffChange(user_id=user.id, actor_id=actor.id, action="activation_changed", reason=payload.reason))
            audit(db, actor.id, "staff.activation_changed", "user", user.id)
        db.flush()
        response = UserRead.model_validate(user)
    return response


def update_role(db: Session, user_id: UUID, payload: UserRoleUpdate, *, actor_id: UUID) -> UserRead:
    with write_operation(db):
        _staff_lock(db)
        actor = require_actor(db, actor_id, {UserRole.ADMINISTRATOR})
        user = db.scalar(select(User).where(User.id == user_id).with_for_update())
        if user is None:
            raise NotFound("Staff account not found.")
        if user.password_hash is None:
            raise Conflict("Accept the staff invitation before changing this account's role.")
        if user.role != payload.role.value:
            _protect_last_admin(db, user)
            _protect_assignments(db, user)
            user.role = payload.role.value
            _revoke_sessions(db, user.id)
            db.add(StaffChange(user_id=user.id, actor_id=actor.id, action="role_changed"))
            audit(db, actor.id, "staff.role_changed", "user", user.id)
        db.flush()
        response = UserRead.model_validate(user)
    return response
