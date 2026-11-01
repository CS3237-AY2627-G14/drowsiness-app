from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator

from modules.processing.schemas import FrameMeasurements, SensorMeasurements

Label = Literal["awake", "drowsy", "uncertain"]


class RawTelemetry(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    schema_version: Literal[1]
    boot_id: str = Field(min_length=1, max_length=64)
    sequence: int = Field(ge=0)
    uptime_ms: int = Field(ge=0)
    upper_cm: int | None = Field(ge=0, le=1000)
    lower_mm: int | None = Field(gt=0, lt=8000)
    back_adc: int = Field(ge=0, le=4095)
    desk_adc: int = Field(ge=0, le=4095)


class StoredSample(BaseModel):
    received_at: float
    telemetry: RawTelemetry


class RecordingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    participant: str = Field(min_length=1, max_length=100)
    notes: str = Field(default="", max_length=2000)
    role: Literal["development", "held_out"] = "development"


class Recording(RecordingRequest):
    id: str
    started_at: float
    stopped_at: float | None = None
    sample_count: int = 0
    provenance: Literal["staged_posture"] = "staged_posture"


class LabelInterval(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: FiniteFloat
    end: FiniteFloat
    label: Label
    posture: str = Field(default="", max_length=200)

    @model_validator(mode="after")
    def validate_interval(self) -> "LabelInterval":
        if self.end <= self.start:
            raise ValueError("Interval end must be after start")
        return self


class RecordingDetail(BaseModel):
    recording: Recording
    samples: list[StoredSample]
    intervals: list[LabelInterval]
    observations: list["CameraObservation"] = Field(default_factory=list)


class CameraObservation(BaseModel):
    received_at: float
    frame: FrameMeasurements
    sensors: dict[str, SensorMeasurements]


class TrainingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recording_ids: list[str] = Field(min_length=3)


class ModelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_id: str | None = None


class TrainingJob(BaseModel):
    id: str
    status: Literal["running", "complete", "failed"]
    created_at: float
    report: dict[str, Any] | None = None
    error: str | None = None


class LiveTelemetry(BaseModel):
    sample: StoredSample | None = None
    age_seconds: float | None = None
    active_recording: str | None = None
    active_model: str | None = None
    candidate_model: str | None = None
    score: float | None = None
    candidate_score: float | None = None
    possible_drowsy: bool | None = None
    present: bool | None = None
    unavailable_reason: str | None = None
    storage_ready: bool = False
