from typing import Any

from modules.processing.calibration.schemas import (
    LabelInterval,
    LiveTelemetry,
    Recording,
    RecordingDetail,
    RecordingRequest,
    TrainingJob,
)
from modules.processing.calibration.service import CalibrationService
from modules.processing.services.frame_processing_service import FrameProcessingService


class CalibrationFacade:
    def __init__(
        self,
        calibration_service: CalibrationService,
        frame_processing_service: FrameProcessingService,
    ) -> None:
        self._calibration_service = calibration_service
        self._frame_processing_service = frame_processing_service

    def live(self) -> LiveTelemetry:
        return self._calibration_service.live()

    async def list_recordings(self) -> list[Recording]:
        return await self._calibration_service.list_recordings()

    async def start_recording(self, request: RecordingRequest) -> Recording:
        return await self._calibration_service.start_recording(request)

    async def stop_recording(self, recording_id: str) -> Recording:
        return await self._calibration_service.stop_recording(recording_id)

    async def detail(self, recording_id: str) -> RecordingDetail:
        return await self._calibration_service.detail(recording_id)

    async def label(self, recording_id: str, intervals: list[LabelInterval]) -> None:
        await self._calibration_service.label(recording_id, intervals)

    async def jobs(self) -> list[TrainingJob]:
        return await self._calibration_service.jobs()

    async def train(self, recording_ids: list[str]) -> TrainingJob:
        return await self._calibration_service.train(recording_ids)

    async def rehearsal(self, recording_id: str) -> dict[str, Any]:
        return await self._calibration_service.rehearsal(recording_id)

    async def activate(self, model_id: str | None) -> None:
        await self._calibration_service.activate(model_id)
        await self._frame_processing_service.reset_sensor_history()
