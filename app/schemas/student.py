"""Students are managed records, not application users."""

from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, Field, StringConstraints

from app.schemas._common import IdentifierText, InputModel, OutputModel, ShortText


AcademicYear = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=32)]
AgeYears = Annotated[int, Field(strict=True, ge=1, le=120)]


class StudentCreate(InputModel):
    student_code: IdentifierText
    name: ShortText
    age: AgeYears
    department: ShortText
    academic_year: AcademicYear
    institution: ShortText


class StudentUpdate(InputModel):
    """Full editable profile; immutable student code is omitted deliberately."""

    name: ShortText
    age: AgeYears
    department: ShortText
    academic_year: AcademicYear
    institution: ShortText


class StudentRead(OutputModel):
    id: UUID
    student_code: IdentifierText
    name: ShortText
    age: AgeYears
    department: ShortText
    academic_year: AcademicYear
    institution: ShortText
    created_by: UUID
    created_at: AwareDatetime
