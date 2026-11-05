"""Authentication from the bearer token, with live account/session checks."""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import hash_token
from app.database.connection import get_db
from app.database.entities import AuthSession, User, utc_now
from app.schemas.user import UserRole
from app.services.errors import AuthenticationRequired, PermissionDenied


bearer = HTTPBearer(auto_error=False)
DatabaseSession = Annotated[Session, Depends(get_db)]


@dataclass(frozen=True)
class Principal:
    user: User
    session: AuthSession


def get_principal(
    db: DatabaseSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer" or not 1 <= len(credentials.credentials) <= 1024:
        raise AuthenticationRequired("Sign in with a valid bearer token.")
    statement = select(AuthSession, User).join(User, User.id == AuthSession.user_id).where(
        AuthSession.token_hash == hash_token(credentials.credentials),
        AuthSession.revoked_at.is_(None), AuthSession.expires_at > utc_now(),
        User.is_active.is_(True), User.password_hash.is_not(None),
    ).execution_options(populate_existing=True)
    row = db.execute(statement).first()
    if row is None:
        raise AuthenticationRequired("Your session is invalid or expired. Sign in again.")
    return Principal(user=row.User, session=row.AuthSession)


def get_current_user(principal: Annotated[Principal, Depends(get_principal)]) -> User:
    return principal.user


CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


def require_roles(*roles: UserRole):
    allowed = set(roles)
    def dependency(user: CurrentUser) -> User:
        if user.role not in allowed:
            raise PermissionDenied("Your role cannot perform this operation.")
        return user
    return dependency


AdminUser = Annotated[User, Depends(require_roles(UserRole.ADMINISTRATOR))]
CounsellorUser = Annotated[User, Depends(require_roles(UserRole.COUNSELLOR))]
