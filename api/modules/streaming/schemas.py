from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from modules.processing.facade import DrowsinessResult, MinuteSummary
from modules.sessions.facade import PublisherSession


class AuthenticateMessage(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    seat_id: int = Field(gt=0)
    token: SecretStr = Field(min_length=1, max_length=512)
    diagnostics: bool = False


class StreamingRecord(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)
    publisher: PublisherSession
    last_received_at: float
    last_frame_id: int = 0
    last_capture_ms: float = -1.0
    received_frames: int = 0
    received_bytes: int = 0
    sample_at: float
    sample_received_frames: int = 0
    sample_processed_frames: int = 0
    sample_received_bytes: int = 0


class StreamDiagnostics(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)
    received_frames: int
    processed_frames: int
    replaced_frames: int
    stale_frames: int
    received_fps: float
    processed_fps: float
    upload_kbps: float
    last_received_frame_id: int
    pending_frames: int
    in_flight: bool


class StreamStatus(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)
    diagnostics: StreamDiagnostics
    detection: DrowsinessResult | None


class DetectionSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)
    captured_at_ms: float
    ear: float | None
    fatigue_probability: float | None
    fsr_raw: int | None
    tof_distance_mm: int | None
    minute: MinuteSummary
    alert: bool
    face_detected: bool


class StreamResponse(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)
    type: Literal["status"] = "status"
    detection: DetectionSnapshot | None
    diagnostics: StreamDiagnostics | None = None


class SocketConnection(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)
    connection_id: UUID
    diagnostics: bool
