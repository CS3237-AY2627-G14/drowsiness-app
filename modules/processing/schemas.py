from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, computed_field


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


class FrameMeasurements(BaseModel):
    """Raw EAR and CNN measurements returned for one camera frame."""

    model_config = ConfigDict(frozen=True, strict=True)
    connection_id: UUID
    frame_id: int
    captured_at_ms: float
    left_ear: float | None = None
    right_ear: float | None = None
    fatigue_probability: float | None = None
    processing_ms: float = 0.0
    error: str | None = None


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
    minute: MinuteSummary
    processing_ms: float
    alert: bool

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
