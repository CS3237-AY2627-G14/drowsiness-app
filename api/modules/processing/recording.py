from typing import Protocol

from modules.processing.schemas import (
    FrameMeasurements,
    SensorMeasurements,
    StoredSample,
)


class MeasurementRecorder(Protocol):
    def get_recording_id(self) -> str | None: ...
    async def record_sensor_sample(
        self, sample: StoredSample, comparisons: dict[str, SensorMeasurements]
    ) -> None: ...
    def observe_camera(
        self,
        recording_id: str | None,
        received_at: float,
        frame: FrameMeasurements,
        comparisons: dict[str, SensorMeasurements],
        generation: int = 0,
    ) -> None: ...
    def reset_sensor_history(self) -> None: ...
