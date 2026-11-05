"""Shared request/response settings and reusable field definitions."""

from typing import Annotated, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
IdentifierText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
NotesText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]
PositiveMeasurement = Annotated[float, Field(strict=True, gt=0, allow_inf_nan=False)]


class InputModel(BaseModel):
    """Reject unknown request fields, including client-supplied audit/status data."""

    model_config = ConfigDict(extra="forbid")


class OutputModel(BaseModel):
    """Read ORM attributes while exposing only declared response fields."""

    model_config = ConfigDict(from_attributes=True, extra="ignore")


Item = TypeVar("Item")


class Page(OutputModel, Generic[Item]):
    items: list[Item]
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
