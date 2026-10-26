import asyncio
import logging
import time
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from core.clock import MonotonicTimer, Timer
from core.config import Settings
from modules.processing.exceptions import ProcessingException
from modules.processing.inference.frame_buffer import FrameBuffer
from modules.processing.inference.frame_predictor import FramePredictor
from modules.processing.mqtt_result_publisher import MqttResultPublisherPort
from modules.processing.publishing import (
    SeatStatusPublisher,
    SeatStatusUpdate,
    StudentSeatStatus,
)
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
from modules.processing.utils.drowsiness_rules import (
    evaluate_measurements,
    reclassify_latest_sample,
)

logger = logging.getLogger(__name__)
SENSOR_STATUS_INTERVAL_SECONDS = 1.0


class SeatRow(BaseModel):
    """Latest sensor reading and minute window for one seat."""

    model_config = ConfigDict(frozen=True, strict=True)

    fsr_raw: int | None = None
    tof_distance_mm: int | None = None
    present: bool | None = None
    captured_at_ms: float | None = None
    received_at: float | None = None
    latest_camera: FrameMeasurements | None = None
    detection_state: DetectionState = DetectionState()


class FrameProcessingService:
    """Admit camera frames, schedule inference and maintain per-seat results."""

    def __init__(
        self,
        processing_registry: ProcessingRegistry,
        frame_buffer: FrameBuffer,
        frame_predictor: FramePredictor,
        settings: Settings,
        timer: Timer | None = None,
        status_publisher: SeatStatusPublisher | None = None,
        mqtt_result_publisher: MqttResultPublisherPort | None = None,
    ) -> None:
        self._processing_registry = processing_registry
        self._frame_buffer = frame_buffer
        self._frame_predictor = frame_predictor
        self._settings = settings
        self._timer = timer if timer is not None else MonotonicTimer()
        self._status_publisher = status_publisher
        self._mqtt_result_publisher = mqtt_result_publisher
        self._available = asyncio.Event()
        self._tasks: list[asyncio.Task[None]] = []
        self._failed = False
        self._seat_rows: dict[int, SeatRow] = {}
        self._connection_by_seat: dict[int, UUID] = {}
        self._last_sensor_publish_at: dict[int, float] = {}

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

    async def associate_seat(self, connection_id: UUID, seat_id: int) -> None:
        record = self._get_active_record(connection_id)
        previous_seat = record.seat_id
        if (
            previous_seat is not None
            and self._connection_by_seat.get(previous_seat) == connection_id
        ):
            del self._connection_by_seat[previous_seat]
        self._connection_by_seat[seat_id] = connection_id
        self._processing_registry.save(
            connection_id, record.model_copy(update={"seat_id": seat_id})
        )

    async def submit_sensor_measurements(
        self, seat_id: int, measurements: SensorMeasurements
    ) -> None:
        row = self._seat_rows.get(seat_id, SeatRow())
        if (
            row.captured_at_ms is not None
            and measurements.captured_at_ms <= row.captured_at_ms
        ):
            return
        previous_drowsy = self._drowsy_seat_ids()
        received_at = self._timer.now()
        updated_row = self._update_sensor_row(row, measurements, received_at)
        self._seat_rows[seat_id] = updated_row
        self._save_connection_detection(seat_id, updated_row.detection_state)
        self._enqueue_started_alert(row.detection_state, updated_row.detection_state)
        self._publish_seat(seat_id, previous_drowsy, sensor_driven=True)

    def _update_sensor_row(
        self, row: SeatRow, measurements: SensorMeasurements, received_at: float
    ) -> SeatRow:
        camera = row.latest_camera
        detection_state = row.detection_state
        if camera is not None and detection_state.samples:
            measured = camera.model_copy(
                update={
                    "fsr_raw": measurements.fsr_raw,
                    "tof_distance_mm": measurements.tof_distance_mm,
                    "present": measurements.present,
                }
            )
            detection_state = reclassify_latest_sample(
                detection_state, measured, self._settings
            )
        return row.model_copy(
            update={
                "fsr_raw": measurements.fsr_raw,
                "tof_distance_mm": measurements.tof_distance_mm,
                "present": measurements.present,
                "captured_at_ms": measurements.captured_at_ms,
                "received_at": received_at,
                "detection_state": detection_state,
            }
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
        record = self._processing_registry.get(connection_id)
        seat_id = record.seat_id if record is not None else None
        self._processing_registry.remove(connection_id)
        self._frame_buffer.discard_pending(connection_id)
        if seat_id is None or self._connection_by_seat.get(seat_id) != connection_id:
            return
        del self._connection_by_seat[seat_id]
        row = self._seat_rows.get(seat_id)
        if row is None or row.detection_state.detection is None:
            return
        previous_drowsy = self._drowsy_seat_ids()
        self._seat_rows[seat_id] = row.model_copy(
            update={"latest_camera": None, "detection_state": DetectionState()}
        )
        self._publish_seat(seat_id, previous_drowsy, sensor_driven=False)

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
            self._processing_registry.save(measurements.connection_id, updated_record)
            return
        seat_id = record.seat_id
        previous_drowsy = self._drowsy_seat_ids() if seat_id is not None else ()
        if seat_id is None:
            detection_state = evaluate_measurements(
                record.detection_state, measurements, self._settings
            )
        else:
            detection_state = self._update_seat_detection(seat_id, measurements)
        updated_record = record.model_copy(
            update={
                "detection_state": detection_state,
                "processed_frames": record.processed_frames + 1,
            }
        )
        self._processing_registry.save(measurements.connection_id, updated_record)
        self._enqueue_started_alert(record.detection_state, detection_state)
        if seat_id is not None:
            self._publish_seat(seat_id, previous_drowsy, sensor_driven=False)

    def _enqueue_started_alert(
        self, previous_state: DetectionState, current_state: DetectionState
    ) -> None:
        if self._mqtt_result_publisher is None:
            return
        previous_detection = previous_state.detection
        detection = current_state.detection
        if (
            detection is not None
            and detection.alert
            and (previous_detection is None or not previous_detection.alert)
        ):
            self._mqtt_result_publisher.enqueue_alert()

    def _update_seat_detection(
        self, seat_id: int, measurements: FrameMeasurements
    ) -> DetectionState:
        row = self._seat_rows.get(seat_id, SeatRow())
        measured = self._with_fresh_sensor(row, measurements)
        detection_state = evaluate_measurements(
            row.detection_state, measured, self._settings
        )
        updated_row = row.model_copy(
            update={
                "latest_camera": measurements,
                "detection_state": detection_state,
            }
        )
        self._seat_rows[seat_id] = updated_row
        self._connection_by_seat[seat_id] = measurements.connection_id
        return detection_state

    def _with_fresh_sensor(
        self, row: SeatRow, measurements: FrameMeasurements
    ) -> FrameMeasurements:
        fsr_raw, tof_distance_mm = self._get_fresh_sensor_values(row)
        if fsr_raw is None:
            return measurements
        return measurements.model_copy(
            update={
                "fsr_raw": fsr_raw,
                "tof_distance_mm": tof_distance_mm,
                "present": row.present,
            }
        )

    def _get_fresh_sensor_values(self, row: SeatRow) -> tuple[int | None, int | None]:
        if (
            row.received_at is None
            or row.fsr_raw is None
            or self._timer.now() - row.received_at
            > self._settings.mqtt_sensor_max_age_seconds
        ):
            return None, None
        return row.fsr_raw, row.tof_distance_mm

    def _save_connection_detection(
        self, seat_id: int, detection_state: DetectionState
    ) -> None:
        connection_id = self._connection_by_seat.get(seat_id)
        if connection_id is None:
            return
        record = self._processing_registry.get(connection_id)
        if record is None:
            return
        self._processing_registry.save(
            connection_id,
            record.model_copy(update={"detection_state": detection_state}),
        )

    def _drowsy_seat_ids(self) -> tuple[int, ...]:
        return tuple(
            sorted(
                seat_id
                for seat_id, row in self._seat_rows.items()
                if row.detection_state.detection is not None
                and row.detection_state.detection.alert
            )
        )

    def _publish_seat(
        self,
        seat_id: int,
        previous_drowsy: tuple[int, ...],
        *,
        sensor_driven: bool,
    ) -> None:
        if self._status_publisher is None:
            return
        current_drowsy = self._drowsy_seat_ids()
        alert_changed = previous_drowsy != current_drowsy
        if sensor_driven:
            now = self._timer.now()
            if not alert_changed and not self._is_sensor_publish_due(seat_id, now):
                return
            self._last_sensor_publish_at[seat_id] = now
        student_status = self._build_student_status(seat_id)
        lecturer_seats = current_drowsy if alert_changed else None
        update = SeatStatusUpdate(student=student_status, drowsy_seats=lecturer_seats)
        self._status_publisher.publish(update)

    def _is_sensor_publish_due(self, seat_id: int, now: float) -> bool:
        last_published = self._last_sensor_publish_at.get(seat_id)
        return (
            last_published is None
            or now - last_published >= SENSOR_STATUS_INTERVAL_SECONDS
        )

    def _build_student_status(self, seat_id: int) -> StudentSeatStatus:
        row = self._seat_rows[seat_id]
        detection = row.detection_state.detection
        drowsy = detection is not None and detection.alert
        return StudentSeatStatus(seat_id=seat_id, drowsy=drowsy)

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
