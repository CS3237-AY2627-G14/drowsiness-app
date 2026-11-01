import asyncio
import logging
from typing import Any
from uuid import uuid4

from core.clock import Clock, SystemClock
from core.config import Settings
from modules.processing.calibration.features import SensorWindow, baseline_result
from modules.processing.calibration.rehearsal import summarize_rehearsal
from modules.processing.calibration.repository import CalibrationRepository
from modules.processing.calibration.schemas import (
    CameraObservation,
    LabelInterval,
    LiveTelemetry,
    RawTelemetry,
    Recording,
    RecordingDetail,
    RecordingRequest,
    StoredSample,
    TrainingJob,
)
from modules.processing.calibration.training import (
    load_artifact,
    predict_scores,
    train_model,
)
from modules.processing.schemas import FrameMeasurements, SensorMeasurements

logger = logging.getLogger(__name__)


class CalibrationService:
    def __init__(
        self,
        calibration_repository: CalibrationRepository,
        settings: Settings,
        clock: Clock | None = None,
    ) -> None:
        self._calibration_repository = calibration_repository
        self._settings = settings
        self._clock = clock if clock is not None else SystemClock()
        self._window = SensorWindow()
        self._latest: StoredSample | None = None
        self._active_recording: Recording | None = None
        self._active_model: str | None = None
        self._artifact: dict[str, Any] | None = None
        self._candidate_model: str | None = None
        self._candidate: dict[str, Any] | None = None
        self._retired_boots: set[str] = set()
        self._evidence: SensorMeasurements | None = None
        self._candidate_score: float | None = None
        self._last_prediction = -1.0
        self._task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        self._pending_observations: dict[int, CameraObservation] = {}
        self.ready = False

    def now(self) -> float:
        return self._clock.now().timestamp()

    @property
    def has_active_model(self) -> bool:
        return self._active_model is not None

    async def start(self) -> None:
        self.ready = await asyncio.to_thread(self._calibration_repository.is_ready)
        if not self.ready:
            logger.warning(
                "Calibration storage unavailable; run "
                "python -m modules.processing.calibration init"
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
        if model_id is not None:
            # Refuse to silently replace an incompatible model with legacy rules.
            self._artifact = await asyncio.to_thread(
                load_artifact,
                self._calibration_repository.directory,
                model_id,
                self._settings.sensor_presence_mm,
            )
            self._active_model = model_id

    async def stop(self) -> None:
        if self._task is not None:
            await self._task
        if self._active_recording is not None:
            await self.stop_recording(self._active_recording.id)

    def require_storage(self) -> None:
        if not self.ready:
            raise RuntimeError(
                "Initialize storage with "
                "uv run python -m modules.processing.calibration init; restart API"
            )

    async def receive(self, telemetry: RawTelemetry) -> None:
        async with self._lock:
            if telemetry.boot_id in self._retired_boots:
                return
            if self._latest is not None:
                previous = self._latest.telemetry
                if telemetry.boot_id == previous.boot_id:
                    if (
                        telemetry.sequence <= previous.sequence
                        or telemetry.uptime_ms <= previous.uptime_ms
                    ):
                        return
                else:
                    self._retired_boots.add(previous.boot_id)
                    self._evidence = None
                    self._last_prediction = -1.0
            sample = StoredSample(received_at=self.now(), telemetry=telemetry)
            if self._latest and sample.received_at - self._latest.received_at > 0.6:
                self._evidence = None
                self._candidate_score = None
                self._last_prediction = -1.0
            self._latest = sample
            self._window.add(sample)
            if self._active_recording is not None:
                await self._calibration_repository.add_sample(
                    self._active_recording.id, sample
                )
                await self._flush_observations(self._active_recording.id)
            if (
                telemetry.lower_mm is None
                or telemetry.lower_mm >= self._settings.sensor_presence_mm
            ):
                self._evidence = SensorMeasurements(
                    drowsy=None,
                    captured_at_ms=sample.received_at * 1000,
                    present=False if telemetry.lower_mm is not None else None,
                    model_version=self._active_model,
                    unavailable_reason="unoccupied"
                    if telemetry.lower_mm is not None
                    else "invalid_lower_distance",
                )
                return
            if sample.received_at - self._last_prediction >= 1:
                self._last_prediction = sample.received_at
                self._predict(sample)

    def _predict(self, sample: StoredSample) -> None:
        features = self._window.features()
        self._candidate_score = (
            predict_scores(self._candidate["estimator"], [features])[0]
            if self._candidate is not None and features is not None
            else None
        )
        score: float | None = None
        possible: bool | None = None
        reason: str | None = None
        if self._artifact is not None:
            if features is None:
                reason = "insufficient_valid_window"
            else:
                score = predict_scores(self._artifact["estimator"], [features])[0]
                possible = score >= self._artifact["threshold"]
        else:
            possible = baseline_result(sample, self._settings.sensor_presence_mm)
            if possible is None:
                reason = "legacy_no_result"
        self._evidence = SensorMeasurements(
            drowsy=possible,
            captured_at_ms=sample.received_at * 1000,
            present=True,
            score=score,
            model_version=self._active_model,
            unavailable_reason=reason,
        )

    def evidence(self) -> SensorMeasurements:
        if (
            self._evidence is None
            or self.now() - self._evidence.captured_at_ms / 1000
            > self._settings.mqtt_sensor_max_age_seconds
        ):
            return SensorMeasurements(
                drowsy=None,
                present=None,
                captured_at_ms=self.now() * 1000,
                model_version=self._active_model,
                unavailable_reason="telemetry_stale_or_warming_up",
            )
        return self._evidence

    def live(self) -> LiveTelemetry:
        evidence = self.evidence()
        return LiveTelemetry(
            sample=self._latest,
            age_seconds=max(0, self.now() - self._latest.received_at)
            if self._latest
            else None,
            active_recording=self._active_recording.id
            if self._active_recording
            else None,
            active_model=self._active_model,
            candidate_model=self._candidate_model,
            score=evidence.score,
            candidate_score=self._candidate_score
            if evidence.unavailable_reason != "telemetry_stale_or_warming_up"
            else None,
            possible_drowsy=evidence.drowsy,
            present=evidence.present,
            unavailable_reason=evidence.unavailable_reason,
            storage_ready=self.ready,
        )

    def comparisons(self) -> dict[str, SensorMeasurements]:
        evidence = self.evidence()
        baseline = (
            baseline_result(self._latest, self._settings.sensor_presence_mm)
            if self._latest
            else None
        )
        if evidence.unavailable_reason == "telemetry_stale_or_warming_up":
            baseline = None
        candidate = (
            self._candidate_score >= self._candidate["threshold"]
            if self._candidate_score is not None
            and self._candidate is not None
            and evidence.present is True
            and evidence.unavailable_reason != "telemetry_stale_or_warming_up"
            else None
        )
        return {
            "active": evidence,
            "baseline": evidence.model_copy(
                update={"drowsy": baseline, "model_version": None}
            ),
            "candidate": evidence.model_copy(
                update={"drowsy": candidate, "model_version": self._candidate_model}
            ),
        }

    def observe_camera(
        self,
        recording_id: str | None,
        received_at: float,
        frame: FrameMeasurements,
        comparisons: dict[str, SensorMeasurements],
    ) -> None:
        if (
            self._active_recording is not None
            and self._active_recording.id == recording_id
            and frame.error is None
        ):
            self._pending_observations[int(received_at)] = CameraObservation(
                received_at=received_at,
                frame=frame,
                sensors=comparisons,
            )

    async def _flush_observations(self, recording_id: str) -> None:
        pending = self._pending_observations.copy()
        self._pending_observations.clear()
        if pending:
            await self._calibration_repository.save_observations(recording_id, pending)

    async def rehearsal(self, recording_id: str) -> dict[str, Any]:
        detail = await self.detail(recording_id)
        return summarize_rehearsal(detail, self._settings)

    async def list_recordings(self) -> list[Recording]:
        self.require_storage()
        return await self._calibration_repository.list_recordings()

    async def start_recording(self, request: RecordingRequest) -> Recording:
        self.require_storage()
        async with self._lock:
            if self._active_recording is not None:
                raise ValueError("Stop the current recording first")
            recording = Recording(
                id=uuid4().hex, started_at=self.now(), **request.model_dump()
            )
            await self._calibration_repository.save_recording(recording)
            self._active_recording = recording
            return recording

    async def stop_recording(self, recording_id: str) -> Recording:
        self.require_storage()
        async with self._lock:
            if (
                self._active_recording is None
                or self._active_recording.id != recording_id
            ):
                raise ValueError("Recording is not active")
            recording = self._active_recording.model_copy(
                update={"stopped_at": self.now()}
            )
            self._active_recording = None
            await self._flush_observations(recording_id)
            await self._calibration_repository.save_recording(recording)
            return recording

    async def detail(self, recording_id: str) -> RecordingDetail:
        self.require_storage()
        return await self._calibration_repository.get_detail(recording_id)

    async def label(self, recording_id: str, intervals: list[LabelInterval]) -> None:
        self.require_storage()
        async with self._lock:
            detail = await self._calibration_repository.get_detail(recording_id)
            ordered = sorted(intervals, key=lambda item: item.start)
            for index, interval in enumerate(ordered):
                if interval.start < detail.recording.started_at or interval.end > (
                    detail.recording.stopped_at or self.now()
                ):
                    raise ValueError("Labels must be inside the recording")
                if index and interval.start < ordered[index - 1].end:
                    raise ValueError("Label intervals cannot overlap")
            await self._calibration_repository.replace_labels(recording_id, ordered)

    async def jobs(self) -> list[TrainingJob]:
        self.require_storage()
        return await self._calibration_repository.list_jobs()

    async def train(self, recording_ids: list[str]) -> TrainingJob:
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
            artifact = await asyncio.to_thread(
                load_artifact,
                self._calibration_repository.directory,
                job.id,
                self._settings.sensor_presence_mm,
            )
            self._candidate = artifact
            self._candidate_model = job.id
            completed = job.model_copy(update={"status": "complete", "report": report})
        except Exception as error:
            logger.exception("Sensor training failed")
            completed = job.model_copy(update={"status": "failed", "error": str(error)})
        await self._calibration_repository.save_job(completed)

    async def activate(self, model_id: str | None) -> None:
        self.require_storage()
        async with self._lock:
            artifact = None
            if model_id is not None:
                jobs = await self._calibration_repository.list_jobs()
                if not any(
                    job.id == model_id and job.status == "complete" for job in jobs
                ):
                    raise ValueError("Select a completed model")
                artifact = await asyncio.to_thread(
                    load_artifact,
                    self._calibration_repository.directory,
                    model_id,
                    self._settings.sensor_presence_mm,
                )
            await self._calibration_repository.save_selection(model_id)
            self._artifact = artifact
            self._active_model = model_id
            self._window.clear()
            self._evidence = None
            self._last_prediction = -1.0
            self._candidate_score = None
