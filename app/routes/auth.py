from fastapi import APIRouter, Request, Response

from app.auth.permissions import CurrentPrincipal, CurrentUser, DatabaseSession
from app.schemas.user import InvitationAccept, LoginRequest, LoginResponse, UserRead
from app.services import auth_service


router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request, db: DatabaseSession):
    return auth_service.login(db, payload, client_ip=request.client.host if request.client else "unknown")


@router.get("/me", response_model=UserRead)
def me(user: CurrentUser):
    return UserRead.model_validate(user)


@router.post("/logout", status_code=204)
def logout(db: DatabaseSession, principal: CurrentPrincipal):
    auth_service.logout(db, principal.session.id, actor_id=principal.user.id)
    return Response(status_code=204)


@router.post("/invitations/accept", response_model=UserRead)
def accept_invitation(payload: InvitationAccept, db: DatabaseSession):
    return auth_service.accept_invitation(db, payload)
