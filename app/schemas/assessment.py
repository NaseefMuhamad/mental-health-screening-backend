from typing import Annotated,Literal
from uuid import UUID
from pydantic import AwareDatetime,Field
from app.schemas._common import InputModel,OutputModel

class AssessmentCreate(InputModel):
    # These are audited dataset support bounds, not clinical or questionnaire cutoffs.
    sleep_hours: Annotated[float,Field(strict=True,ge=4,le=9,allow_inf_nan=False)]
    screen_time: Annotated[float,Field(strict=True,ge=2,le=10,allow_inf_nan=False)]
    assignment_load: Annotated[int,Field(strict=True,ge=1,le=9)]
    exam_pressure: Annotated[int,Field(strict=True,ge=1,le=10)]
    social_support: Annotated[int,Field(strict=True,ge=1,le=10)]
    protocol: Literal['demo_dataset_scales_v1'] = 'demo_dataset_scales_v1'

class AssessmentRead(OutputModel):
    id: UUID
    screening_id: UUID
    recorded_by: UUID
    inputs: dict[str,float|int|str]
    protocol: str
    created_at: AwareDatetime
