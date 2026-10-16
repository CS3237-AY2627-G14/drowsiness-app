import asyncio
import logging
from uuid import UUID

from core.clock import MonotonicTimer, Timer
from core.config import Settings
from modules.processing.exceptions import ProcessingException
from modules.processing.inference.frame_buffer import FrameBuffer
from modules.processing.inference.frame_predictor import FramePredictor
from modules.processing.repositories.registry import ProcessingRegistry
from modules.processing.schemas import (
    FrameInput,
    FrameMeasurements,
    ProcessingRecord,
    ProcessingStatus,
    QueuedFrame,
)
from modules.processing.utils.drowsiness_rules import evaluate_measurements

logger = logging.getLogger(__name__)


class FrameProcessingService:
    """Admit camera frames, schedule inference and maintain per-camera results."""

    def __init__(
        self,
        processing_registry: ProcessingRegistry,
        frame_buffer: FrameBuffer,
        frame_predictor: FramePredictor,
        settings: Settings,
        timer: Timer | None = None,
    ) -> None:
        self._processing_registry = processing_registry
        self._frame_buffer = frame_buffer
        self._frame_predictor = frame_predictor
        self._settings = settings
        self._timer = timer if timer is not None else MonotonicTimer()
        self._available = asyncio.Event()
        self._tasks: list[asyncio.Task[None]] = []
        self._failed = False

    def start(self, workers: int) -> None:
        self._tasks = [
            asyncio.create_task(self._process_frames()) for _ in range(workers)
        ]
        for task in self._tasks:
            task.add_done_callback(self._handle_processor_completion)

    def _handle_processor_completion(self, task: asyncio.Task[None]) -> None:
        if task.cancelled():
            return
        failure = task.exception()
        if failure is not None:
            logger.error("Frame processing task failed", exc_info=failure)
            self._failed = True
            self._available.set()

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def open_connection(self, connection_id: UUID) -> None:
        if self._failed:
            raise ProcessingException("server_unavailable")
        self._processing_registry.save(connection_id, ProcessingRecord())

    def _get_active_record(self, connection_id: UUID) -> ProcessingRecord:
        if self._failed:
            raise ProcessingException("server_unavailable")
        record = self._processing_registry.get(connection_id)
        if record is None:
            raise ProcessingException("stream_closed")
        if record.error:
            raise ProcessingException(record.error)
        return record

    async def submit_frame(self, connection_id: UUID, frame: FrameInput) -> None:
        record = self._get_active_record(connection_id)
        received_at = self._timer.now()
        work = QueuedFrame(
            connection_id=connection_id, frame=frame, received_at=received_at
        )
        was_replaced = self._frame_buffer.put_latest(work)
        updated_record = record.model_copy(
            update={
                "replaced_frames": record.replaced_frames + int(was_replaced),
            }
        )
        self._processing_registry.save(connection_id, updated_record)
        self._available.set()

    async def get_status(self, connection_id: UUID) -> ProcessingStatus:
        record = self._get_active_record(connection_id)
        return ProcessingStatus(
            processed_frames=record.processed_frames,
            replaced_frames=record.replaced_frames,
            stale_frames=record.stale_frames,
            pending_frames=self._frame_buffer.pending_count(connection_id),
            in_flight=self._frame_buffer.is_in_flight(connection_id),
            detection=record.detection_state.detection,
        )

    async def close_connection(self, connection_id: UUID) -> None:
        self._processing_registry.remove(connection_id)
        self._frame_buffer.discard_pending(connection_id)

    async def _process_frames(self) -> None:
        while not self._failed:
            batch = self._take_fresh_batch()
            if not batch:
                self._available.clear()
                await self._available.wait()
                continue
            try:
                batch_measurements = await self._frame_predictor.predict_batch(batch)
            finally:
                self._frame_buffer.release_batch(batch)
            for measurements in batch_measurements:
                self._apply_frame_measurements(measurements)
            self._available.set()

    def _apply_frame_measurements(self, measurements: FrameMeasurements) -> None:
        record = self._processing_registry.get(measurements.connection_id)
        if record is None:
            return
        if measurements.error:
            updated_record = record.model_copy(update={"error": measurements.error})
        else:
            detection_state = evaluate_measurements(
                record.detection_state, measurements, self._settings
            )
            updated_record = record.model_copy(
                update={
                    "detection_state": detection_state,
                    "processed_frames": record.processed_frames + 1,
                }
            )
        self._processing_registry.save(measurements.connection_id, updated_record)

    def _take_fresh_batch(self) -> tuple[QueuedFrame, ...]:
        now = self._timer.now()
        fresh: list[QueuedFrame] = []
        while len(fresh) < self._settings.inference_batch_size:
            remaining_capacity = self._settings.inference_batch_size - len(fresh)
            selected = self._frame_buffer.claim_batch(remaining_capacity)
            if not selected:
                break
            for work in selected:
                if now - work.received_at > self._settings.max_pending_seconds:
                    record = self._processing_registry.get(work.connection_id)
                    if record is not None:
                        updated_record = record.model_copy(
                            update={"stale_frames": record.stale_frames + 1}
                        )
                        self._processing_registry.save(
                            work.connection_id, updated_record
                        )
                    self._frame_buffer.release_batch((work,))
                else:
                    fresh.append(work)
        return tuple(fresh)
