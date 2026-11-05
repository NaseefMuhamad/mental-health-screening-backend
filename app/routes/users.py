from uuid import UUID

from fastapi import APIRouter, Query, Response

from app.auth.permissions import AdminUser, DatabaseSession
from app.schemas._common import Page
from app.schemas.user import InvitationIssued, UserInviteCreate, UserRead, UserRoleUpdate, UserStatusUpdate
from app.services import auth_service


router = APIRouter(prefix="/users", tags=["Staff management"])


@router.get("", response_model=Page[UserRead])
def list_users(db: DatabaseSession, user: AdminUser, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
    return auth_service.list_users(db, actor_id=user.id, offset=offset, limit=limit)


@router.post("/invitations", response_model=InvitationIssued, status_code=201)
def invite(payload: UserInviteCreate, db: DatabaseSession, user: AdminUser):
    return auth_service.issue_invitation(db, payload, actor_id=user.id)


@router.delete("/invitations/{invitation_id}", status_code=204)
def revoke_invitation(invitation_id: UUID, db: DatabaseSession, user: AdminUser):
    auth_service.revoke_invitation(db, invitation_id, actor_id=user.id)
    return Response(status_code=204)


@router.patch("/{user_id}/status", response_model=UserRead)
def change_status(user_id: UUID, payload: UserStatusUpdate, db: DatabaseSession, user: AdminUser):
    return auth_service.update_status(db, user_id, payload, actor_id=user.id)


@router.patch("/{user_id}/role", response_model=UserRead)
def change_role(user_id: UUID, payload: UserRoleUpdate, db: DatabaseSession, user: AdminUser):
    return auth_service.update_role(db, user_id, payload, actor_id=user.id)
