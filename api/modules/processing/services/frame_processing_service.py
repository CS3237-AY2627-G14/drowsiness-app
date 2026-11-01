import asyncio
import logging
import time
from uuid import UUID

from core.clock import MonotonicTimer, Timer
from core.config import Settings
from modules.processing.calibration.service import CalibrationService
from modules.processing.exceptions import ProcessingException
from modules.processing.inference.frame_buffer import FrameBuffer
from modules.processing.inference.frame_predictor import FramePredictor
from modules.processing.mqtt_result_publisher import MqttResultPublisherPort
from modules.processing.repositories.registry import ProcessingRegistry
from modules.processing.schemas import (
    DetectionState,
    FrameInput,
    FrameMeasurements,
    ProcessingRecord,
    ProcessingStatus,
    QueuedFrame,
    SensorMeasurements,
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
        mqtt_result_publisher: MqttResultPublisherPort | None = None,
        calibration_service: CalibrationService | None = None,
    ) -> None:
        self._processing_registry = processing_registry
        self._frame_buffer = frame_buffer
        self._frame_predictor = frame_predictor
        self._settings = settings
        self._timer = timer if timer is not None else MonotonicTimer()
        self._mqtt_result_publisher = mqtt_result_publisher
        self._calibration_service = calibration_service
        self._generation = 0
        self._connection_ids: set[UUID] = set()
        self._available = asyncio.Event()
        self._tasks: list[asyncio.Task[None]] = []
        self._failed = False
        self._sensor_measurements_by_seat: dict[
            int, tuple[SensorMeasurements, float]
        ] = {}

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
        self._connection_ids.add(connection_id)

    async def associate_seat(self, connection_id: UUID, seat_id: int) -> None:
        record = self._get_active_record(connection_id)
        self._processing_registry.save(
            connection_id, record.model_copy(update={"seat_id": seat_id})
        )

    async def submit_sensor_measurements(
        self, seat_id: int, measurements: SensorMeasurements
    ) -> None:
        if (
            seat_id == 1
            and self._calibration_service is not None
            and self._calibration_service.has_active_model
        ):
            return
        latest = self._sensor_measurements_by_seat.get(seat_id)
        if (
            latest is not None
            and measurements.captured_at_ms <= latest[0].captured_at_ms
        ):
            return
        self._sensor_measurements_by_seat[seat_id] = (
            measurements,
            self._timer.now(),
        )

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
        calibration = self._calibration_service if record.seat_id == 1 else None
        work = QueuedFrame(
            connection_id=connection_id,
            frame=frame,
            received_at=received_at,
            sensor=self._snapshot_sensor(record.seat_id),
            generation=self._generation if record.seat_id == 1 else -1,
            calibration_at=calibration.now() if calibration else None,
            recording_id=calibration.live().active_recording if calibration else None,
            comparisons=calibration.comparisons() if calibration else {},
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
        mqtt_alert_publisher = self._mqtt_result_publisher
        last_published_at_ms = (
            mqtt_alert_publisher.last_published_at_ms
            if mqtt_alert_publisher is not None
            else None
        )
        return ProcessingStatus(
            processed_frames=record.processed_frames,
            replaced_frames=record.replaced_frames,
            stale_frames=record.stale_frames,
            pending_frames=self._frame_buffer.pending_count(connection_id),
            in_flight=self._frame_buffer.is_in_flight(connection_id),
            detection=record.detection_state.detection,
            mqtt_alert_sent_recently=last_published_at_ms is not None
            and time.time_ns() / 1_000_000 - last_published_at_ms < 10_000,
        )

    async def close_connection(self, connection_id: UUID) -> None:
        self._processing_registry.remove(connection_id)
        self._connection_ids.discard(connection_id)
        self._frame_buffer.discard_pending(connection_id)

    def _snapshot_sensor(self, seat_id: int | None) -> SensorMeasurements:
        if seat_id == 1 and self._calibration_service is not None:
            live = self._calibration_service.live()
            if live.active_model is not None or live.sample is not None:
                return self._calibration_service.evidence()
        entry = self._sensor_measurements_by_seat.get(seat_id) if seat_id else None
        if (
            entry
            and self._timer.now() - entry[1]
            <= self._settings.mqtt_sensor_max_age_seconds
        ):
            return entry[0]
        return SensorMeasurements(
            drowsy=None,
            present=None,
            captured_at_ms=0.0,
            unavailable_reason="sensor_stale_or_missing",
        )

    async def reset_sensor_history(self) -> None:
        self._generation += 1
        self._sensor_measurements_by_seat.pop(1, None)
        # Existing connections retain ownership; reset their observations and queues.
        for connection_id in tuple(self._connection_ids):
            record = self._processing_registry.get(connection_id)
            if record is not None and record.seat_id == 1:
                self._processing_registry.save(
                    connection_id,
                    record.model_copy(update={"detection_state": DetectionState()}),
                )
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
                work = next(
                    (
                        item
                        for item in batch
                        if item.connection_id == measurements.connection_id
                    ),
                    None,
                )
                if work is not None and work.generation in (-1, self._generation):
                    self._apply_frame_measurements(measurements, work.sensor)
                    if (
                        self._calibration_service is not None
                        and work.calibration_at is not None
                    ):
                        self._calibration_service.observe_camera(
                            work.recording_id,
                            work.calibration_at,
                            measurements,
                            work.comparisons,
                        )
            self._available.set()

    def _apply_frame_measurements(
        self, measurements: FrameMeasurements, sensor: SensorMeasurements | None = None
    ) -> None:
        record = self._processing_registry.get(measurements.connection_id)
        if record is None:
            return
        alert_started = False
        if measurements.error:
            updated_record = record.model_copy(update={"error": measurements.error})
        else:
            sensor_measurements = (
                sensor if sensor is not None else self._snapshot_sensor(record.seat_id)
            )
            if (
                sensor is None
                and record.seat_id is None
                and measurements.sensor_drowsy is not None
            ):
                sensor_measurements = SensorMeasurements(
                    drowsy=measurements.sensor_drowsy,
                    present=measurements.present,
                    captured_at_ms=measurements.captured_at_ms,
                )
            if sensor_measurements is not None:
                measurements = measurements.model_copy(
                    update={
                        "sensor_drowsy": sensor_measurements.drowsy,
                        "present": sensor_measurements.present,
                        "sensor_score": sensor_measurements.score,
                        "sensor_model_version": sensor_measurements.model_version,
                        "sensor_unavailable_reason": (
                            sensor_measurements.unavailable_reason
                        ),
                    }
                )
            detection_state = evaluate_measurements(
                record.detection_state, measurements, self._settings
            )
            previous_detection = record.detection_state.detection
            detection = detection_state.detection
            alert_started = (
                detection is not None
                and detection.alert
                and (previous_detection is None or not previous_detection.alert)
            )
            updated_record = record.model_copy(
                update={
                    "detection_state": detection_state,
                    "processed_frames": record.processed_frames + 1,
                }
            )
        self._processing_registry.save(measurements.connection_id, updated_record)
        if alert_started and self._mqtt_result_publisher is not None:
            self._mqtt_result_publisher.enqueue_alert()

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
