import asyncio
from uuid import uuid4

from core.clock import Clock, SystemClock
from modules.calibration.repository import CalibrationRepository
from modules.calibration.schemas import (
    LabelInterval,
    Recording,
    RecordingDetail,
    RecordingRequest,
)
from modules.processing.facade import (
    CameraObservation,
    FrameMeasurements,
    SensorMeasurements,
    SensorUpdate,
    StoredSample,
)


class RecordingService:
    def __init__(
        self, calibration_repository: CalibrationRepository, clock: Clock | None = None
    ) -> None:
        self._calibration_repository = calibration_repository
        self._clock = clock if clock is not None else SystemClock()
        self._active_recording: Recording | None = None
        self._pending_observations: dict[int, CameraObservation] = {}
        self._latest_observation: tuple[int, CameraObservation] | None = None
        self._lock = asyncio.Lock()
        self.ready = False

    def get_recording_id(self) -> str | None:
        return self._active_recording.id if self._active_recording else None

    def reset_sensor_history(self) -> None:
        self._latest_observation = None

    async def record_sensor_sample(
        self, sample: StoredSample, comparisons: dict[str, SensorMeasurements]
    ) -> None:
        async with self._lock:
            if self._active_recording is not None:
                await self._calibration_repository.add_sample(
                    self._active_recording.id, sample
                )
                self.observe_sensor_update(comparisons)
                await self._flush_observations(self._active_recording.id)

    def now(self) -> float:
        return self._clock.now().timestamp()

    def require_storage(self) -> None:
        if not self.ready:
            raise RuntimeError(
                "Initialize storage with "
                "uv run python -m modules.calibration init; restart API"
            )

    def observe_camera(
        self,
        recording_id: str | None,
        received_at: float,
        frame: FrameMeasurements,
        comparisons: dict[str, SensorMeasurements],
        generation: int = 0,
    ) -> None:
        if (
            self._active_recording is not None
            and self._active_recording.id == recording_id
            and frame.error is None
        ):
            observation = CameraObservation(
                generation=generation,
                received_at=received_at,
                frame=frame,
                sensors=comparisons,
            )
            self._latest_observation = (int(received_at), observation)
            self._pending_observations[int(received_at)] = observation

    def observe_sensor_update(self, comparisons: dict[str, SensorMeasurements]) -> None:
        if self._active_recording is None or self._latest_observation is None:
            return
        second, observation = self._latest_observation
        updated = observation.model_copy(
            update={
                "sensor_updates": [
                    *observation.sensor_updates,
                    SensorUpdate(received_at=self.now(), sensors=comparisons),
                ]
            }
        )
        self._latest_observation = (second, updated)
        self._pending_observations[second] = updated

    async def _flush_observations(self, recording_id: str) -> None:
        pending = self._pending_observations.copy()
        self._pending_observations.clear()
        if pending:
            await self._calibration_repository.save_observations(recording_id, pending)

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
            self._latest_observation = None
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

    async def get_recording(self, recording_id: str) -> RecordingDetail:
        self.require_storage()
        return await self._calibration_repository.get_detail(recording_id)

    async def replace_labels(
        self, recording_id: str, intervals: list[LabelInterval]
    ) -> None:
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
