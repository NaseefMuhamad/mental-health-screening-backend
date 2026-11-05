"""Recorded measurements with explicit units; no diagnostic thresholds."""

from uuid import UUID

from pydantic import AwareDatetime, model_validator
from typing_extensions import Self

from app.schemas._common import InputModel, OutputModel, PositiveMeasurement


class MeasurementCreate(InputModel):
    heart_rate_bpm: PositiveMeasurement
    systolic_mmhg: PositiveMeasurement | None = None
    diastolic_mmhg: PositiveMeasurement | None = None
    pupil_diameter_mm: PositiveMeasurement | None = None

    @model_validator(mode="after")
    def check_pressure_pair(self) -> Self:
        if (self.systolic_mmhg is None) != (self.diastolic_mmhg is None):
            raise ValueError("Supply both blood pressure readings or omit both.")
        if self.systolic_mmhg is not None and self.systolic_mmhg <= self.diastolic_mmhg:
            raise ValueError("Systolic pressure must exceed diastolic pressure.")
        return self


class MeasurementRead(OutputModel):
    id: UUID
    screening_id: UUID
    heart_rate_bpm: PositiveMeasurement
    systolic_mmhg: PositiveMeasurement | None = None
    diastolic_mmhg: PositiveMeasurement | None = None
    pupil_diameter_mm: PositiveMeasurement | None = None
    recorded_by: UUID
    recorded_at: AwareDatetime
