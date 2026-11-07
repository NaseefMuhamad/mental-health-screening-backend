"""Separate simulated category estimates, never a combined diagnosis."""
from enum import Enum
from uuid import UUID
from pydantic import AwareDatetime,model_validator
from app.schemas._common import InputModel,OutputModel,ShortText

class PredictionStatus(str,Enum):
    UNAVAILABLE='unavailable'
    PROCESSING='processing'
    AVAILABLE='available'
    FAILED='failed'

class CategoryLevel(str,Enum):
    LOW='Low'
    MEDIUM='Medium'
    HIGH='High'

class PredictionRequest(InputModel):
    screening_id: UUID

class PredictionRead(OutputModel):
    screening_id: UUID
    status: PredictionStatus
    assessment_id: UUID|None=None
    stress_level: CategoryLevel|None=None
    anxiety_level: CategoryLevel|None=None
    model_version: ShortText|None=None
    generated_at: AwareDatetime|None=None
    message: str|None=None
    prototype: bool=True

    @model_validator(mode='after')
    def validate_outputs(self):
        outputs=(self.stress_level,self.anxiety_level,self.model_version,self.generated_at)
        if self.status==PredictionStatus.AVAILABLE and (any(value is None for value in outputs) or self.assessment_id is None):raise ValueError('Available predictions require both categories, assessment, model version and time.')
        if self.status!=PredictionStatus.AVAILABLE and any(value is not None for value in outputs):raise ValueError('Unavailable predictions must not include model outputs.')
        return self
