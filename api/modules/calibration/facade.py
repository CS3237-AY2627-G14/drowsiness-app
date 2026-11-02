from typing import Any

from modules.calibration.schemas import (
    LabelInterval,
    Recording,
    RecordingDetail,
    RecordingRequest,
    TrainingJob,
)
from modules.calibration.service import CalibrationService
from modules.processing.facade import LiveTelemetry


class CalibrationFacade:
    def __init__(
        self,
        calibration_service: CalibrationService,
    ) -> None:
        self._calibration_service = calibration_service

    def get_live_telemetry(self) -> LiveTelemetry:
        return self._calibration_service.get_live_telemetry()

    async def list_recordings(self) -> list[Recording]:
        return await self._calibration_service.list_recordings()

    async def start_recording(self, request: RecordingRequest) -> Recording:
        return await self._calibration_service.start_recording(request)

    async def stop_recording(self, recording_id: str) -> Recording:
        return await self._calibration_service.stop_recording(recording_id)

    async def get_recording(self, recording_id: str) -> RecordingDetail:
        return await self._calibration_service.get_recording(recording_id)

    async def replace_labels(
        self, recording_id: str, intervals: list[LabelInterval]
    ) -> None:
        await self._calibration_service.replace_labels(recording_id, intervals)

    async def list_training_jobs(self) -> list[TrainingJob]:
        return await self._calibration_service.list_training_jobs()

    async def train_candidate(self, recording_ids: list[str]) -> TrainingJob:
        return await self._calibration_service.train_candidate(recording_ids)

    async def get_rehearsal_report(self, recording_id: str) -> dict[str, Any]:
        return await self._calibration_service.get_rehearsal_report(recording_id)

    async def activate_model(self, model_id: str | None) -> None:
        await self._calibration_service.activate_model(model_id)
