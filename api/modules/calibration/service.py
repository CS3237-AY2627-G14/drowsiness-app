import asyncio
import logging
from typing import Any
from uuid import uuid4

from core.clock import Clock, SystemClock
from core.config import Settings
from modules.calibration.recording_service import RecordingService
from modules.calibration.rehearsal import summarize_rehearsal
from modules.calibration.repository import CalibrationRepository
from modules.calibration.schemas import (
    LabelInterval,
    Recording,
    RecordingDetail,
    RecordingRequest,
    TrainingJob,
)
from modules.calibration.training import train_model
from modules.processing.facade import LiveTelemetry, ProcessingFacade

logger = logging.getLogger(__name__)


class CalibrationService:
    def __init__(
        self,
        calibration_repository: CalibrationRepository,
        settings: Settings,
        processing_facade: ProcessingFacade,
        recording_service: RecordingService,
        clock: Clock | None = None,
    ) -> None:
        self._calibration_repository = calibration_repository
        self._settings = settings
        self._processing_facade = processing_facade
        self._recording_service = recording_service
        self._clock = clock if clock is not None else SystemClock()
        self._task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        self.ready = False

    def now(self) -> float:
        return self._clock.now().timestamp()

    async def start(self) -> None:
        self.ready = await asyncio.to_thread(self._calibration_repository.is_ready)
        self._recording_service.ready = self.ready
        if not self.ready:
            logger.warning(
                "Calibration storage unavailable; run "
                "python -m modules.calibration init"
            )
            return
        for recording in await self._calibration_repository.list_recordings():
            if recording.stopped_at is None:
                await self._calibration_repository.save_recording(
                    recording.model_copy(update={"stopped_at": self.now()})
                )
        for job in await self._calibration_repository.list_jobs():
            if job.status == "running":
                await self._calibration_repository.save_job(
                    job.model_copy(
                        update={
                            "status": "failed",
                            "error": "Training interrupted by API restart",
                        }
                    )
                )
        model_id = await self._calibration_repository.get_selection()
        await self._processing_facade.activate_sensor_model(model_id)

    async def stop(self) -> None:
        if self._task is not None:
            await self._task
        recording_id = self._recording_service.get_recording_id()
        if recording_id is not None:
            await self._recording_service.stop_recording(recording_id)

    def require_storage(self) -> None:
        self._recording_service.require_storage()

    def get_live_telemetry(self) -> LiveTelemetry:
        live = self._processing_facade.get_live_telemetry()
        return live.model_copy(
            update={
                "active_recording": self._recording_service.get_recording_id(),
                "storage_ready": self.ready,
            }
        )

    async def list_recordings(self) -> list[Recording]:
        return await self._recording_service.list_recordings()

    async def start_recording(self, request: RecordingRequest) -> Recording:
        return await self._recording_service.start_recording(request)

    async def stop_recording(self, recording_id: str) -> Recording:
        return await self._recording_service.stop_recording(recording_id)

    async def get_recording(self, recording_id: str) -> RecordingDetail:
        return await self._recording_service.get_recording(recording_id)

    async def replace_labels(
        self, recording_id: str, intervals: list[LabelInterval]
    ) -> None:
        return await self._recording_service.replace_labels(recording_id, intervals)

    async def get_rehearsal_report(self, recording_id: str) -> dict[str, Any]:
        detail = await self.get_recording(recording_id)
        return summarize_rehearsal(detail, self._settings)

    async def list_training_jobs(self) -> list[TrainingJob]:
        self.require_storage()
        return await self._calibration_repository.list_jobs()

    async def train_candidate(self, recording_ids: list[str]) -> TrainingJob:
        self.require_storage()
        async with self._lock:
            if self._task is not None and not self._task.done():
                raise ValueError("A training job is already running")
            if len(recording_ids) != len(set(recording_ids)):
                raise ValueError("Select each recording only once")
            details = [
                await self._calibration_repository.get_detail(recording_id)
                for recording_id in recording_ids
            ]
            if any(detail.recording.stopped_at is None for detail in details):
                raise ValueError("Stop selected recordings before training")
            job = TrainingJob(id=uuid4().hex, status="running", created_at=self.now())
            await self._calibration_repository.save_snapshot(job.id, details)
            await self._calibration_repository.save_job(job)
            self._task = asyncio.create_task(self._train_candidate(job, details))
            return job

    async def _train_candidate(
        self, job: TrainingJob, details: list[RecordingDetail]
    ) -> None:
        try:
            report = await asyncio.to_thread(
                train_model,
                details,
                job.id,
                self._calibration_repository.directory,
                self._settings.sensor_presence_mm,
            )
            await self._processing_facade.select_candidate_model(job.id)
            completed = job.model_copy(update={"status": "complete", "report": report})
        except Exception as error:
            logger.exception("Sensor training failed")
            completed = job.model_copy(update={"status": "failed", "error": str(error)})
        await self._calibration_repository.save_job(completed)

    async def activate_model(self, model_id: str | None) -> None:
        self.require_storage()
        async with self._lock:
            if model_id is not None:
                jobs = await self._calibration_repository.list_jobs()
                if not any(
                    job.id == model_id and job.status == "complete" for job in jobs
                ):
                    raise ValueError("Select a completed model")
            previous_model = self._processing_facade.get_live_telemetry().active_model
            await self._processing_facade.activate_sensor_model(model_id)
            try:
                await self._calibration_repository.save_selection(model_id)
            except Exception:
                await self._processing_facade.activate_sensor_model(previous_model)
                raise
