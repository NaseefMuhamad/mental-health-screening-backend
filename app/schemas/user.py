"""Staff accounts, controlled invitations and login payloads. No student role."""

from enum import Enum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, EmailStr, Field, SecretStr

from app.schemas._common import InputModel, NotesText, OutputModel, ShortText


class UserRole(str, Enum):
    ADMINISTRATOR = "administrator"
    SCREENING_PERSONNEL = "screening_personnel"
    COUNSELLOR = "counsellor"


StaffRole = Literal[UserRole.SCREENING_PERSONNEL, UserRole.COUNSELLOR]
NewPassword = Annotated[SecretStr, Field(min_length=12, max_length=128)]


class UserInviteCreate(InputModel):
    """An administrator invites a staff member; not a public signup payload."""

    name: ShortText
    email: EmailStr
    role: StaffRole


class InvitationRead(OutputModel):
    """Invitation metadata; raw invitation tokens are not returned here."""

    id: UUID
    email: EmailStr
    role: StaffRole
    expires_at: AwareDatetime
    accepted_at: AwareDatetime | None = None


class InvitationAccept(InputModel):
    token: Annotated[SecretStr, Field(min_length=1, max_length=1024)]
    password: NewPassword


class LoginRequest(InputModel):
    email: EmailStr
    password: Annotated[SecretStr, Field(min_length=1, max_length=1024)]


class UserRead(OutputModel):
    id: UUID
    name: ShortText
    email: EmailStr
    role: UserRole
    is_active: bool
    created_at: AwareDatetime


class LoginResponse(OutputModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user: UserRead


class UserProfileUpdate(InputModel):
    name: ShortText


class UserRoleUpdate(InputModel):
    """Admin-only operation; privilege checks belong to the service/dependency."""

    role: UserRole


class UserStatusUpdate(InputModel):
    """Deactivate/reactivate a staff account without deleting its history."""

    is_active: Annotated[bool, Field(strict=True)]
    reason: NotesText
class InvitationIssued(OutputModel):
    """Returned once to the administrator for manual delivery."""

    invitation: InvitationRead
    acceptance_token: str


class BootstrapAdmin(InputModel):
    """Used by the command-line administrator setup."""

    name: ShortText
    email: EmailStr
    password: NewPassword