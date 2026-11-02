from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator

from modules.processing.facade import CameraObservation, StoredSample

Label = Literal["awake", "drowsy", "uncertain"]


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
