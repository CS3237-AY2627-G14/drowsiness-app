from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field


class FrameInput(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)
    frame_id: int
    captured_at_ms: float
    jpeg: bytes


class QueuedFrame(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)
    connection_id: UUID
    frame: FrameInput
    received_at: float
    generation: int = 0
    observed_at: float | None = None
    recording_id: str | None = None


class FrameMeasurements(BaseModel):
    """Measurements used to classify one camera frame."""

    model_config = ConfigDict(frozen=True, strict=True)
    connection_id: UUID
    frame_id: int
    captured_at_ms: float
    left_ear: float | None = None
    right_ear: float | None = None
    fatigue_probability: float | None = None
    sensor_drowsy: bool | None = None
    present: bool | None = None
    processing_ms: float = 0.0
    error: str | None = None
    sensor_score: float | None = None
    sensor_model_version: str | None = None
    sensor_unavailable_reason: str | None = None


class SensorMeasurements(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)
    drowsy: bool | None
    captured_at_ms: float
    present: bool | None
    score: float | None = None
    model_version: str | None = None
    unavailable_reason: str | None = None


class DetectionSample(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    captured_at_ms: float
    drowsy: bool | None


class MinuteSummary(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    valid_samples: int
    drowsy_samples: int
    unavailable_samples: int
    window_seconds: Literal[60] = 60


class DrowsinessResult(BaseModel):
    """Frame measurements interpreted with minute history and alert rules."""

    model_config = ConfigDict(frozen=True, strict=True)

    frame_id: int
    captured_at_ms: float
    ear: float | None
    fatigue_probability: float | None
    sensor_drowsy: bool | None
    present: bool | None
    minute: MinuteSummary
    processing_ms: float
    alert: bool
    sensor_score: float | None = None
    sensor_model_version: str | None = None
    sensor_unavailable_reason: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def face_detected(self) -> bool:
        return self.ear is not None or self.fatigue_probability is not None


class DetectionState(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)
    samples: tuple[DetectionSample, ...] = ()
    detection: DrowsinessResult | None = None


class ProcessingRecord(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)
    seat_id: int | None = None
    processed_frames: int = 0
    replaced_frames: int = 0
    stale_frames: int = 0
    detection_state: DetectionState = DetectionState()
    error: str | None = None


class ProcessingStatus(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)
    processed_frames: int
    replaced_frames: int
    stale_frames: int
    pending_frames: int
    in_flight: bool
    detection: DrowsinessResult | None
    mqtt_alert_sent_recently: bool = False


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
    model_config = ConfigDict(frozen=True)
    received_at: float
    telemetry: RawTelemetry


class SensorUpdate(BaseModel):
    model_config = ConfigDict(frozen=True)
    received_at: float
    sensors: dict[str, SensorMeasurements]


class CameraObservation(BaseModel):
    model_config = ConfigDict(frozen=True)
    received_at: float
    frame: FrameMeasurements
    generation: int = 0
    sensor_updates: list[SensorUpdate] = Field(default_factory=list)
    sensors: dict[str, SensorMeasurements]


class LiveTelemetry(BaseModel):
    model_config = ConfigDict(frozen=True)
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
