from pathlib import Path
from typing import Literal

from pydantic import Field, PositiveInt
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DROWSINESS_", env_file=".env", extra="ignore"
    )

    demo_session_ttl_seconds: PositiveInt
    demo_seat_count: PositiveInt
    max_publishers: PositiveInt
    allowed_origins: tuple[str, ...] = (
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://localhost:3000",
        "https://127.0.0.1:3000",
    )
    model_path: Path = Path("models/drowsiness_mobilenetv4_20261016_013212.pth")
    inference_device: Literal["auto", "cpu", "cuda", "mps"] = "auto"
    inference_workers: PositiveInt | None = None
    inference_batch_size: PositiveInt = 8
    frame_width: PositiveInt = 1280
    frame_height: PositiveInt = 720
    max_frame_bytes: PositiveInt = 1_048_576
    max_pending_seconds: float = Field(default=1.0, gt=0)
    ear_threshold: float = Field(default=0.21, gt=0)
    fatigue_threshold: float = Field(default=0.65, gt=0, le=1)
    fsr_threshold: int = Field(default=50, ge=0, le=4095)
    tof_threshold_mm: int = Field(default=2000, gt=0)
    mqtt_enabled: bool = True
    mqtt_host: str = "127.0.0.1"
    mqtt_port: PositiveInt = 1883
    mqtt_sensor_max_age_seconds: float = Field(default=5.0, gt=0)
