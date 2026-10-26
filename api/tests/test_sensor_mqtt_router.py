import asyncio
import json
from uuid import UUID, uuid4

import pytest

from core.config import Settings
from modules.processing.facade import ProcessingFacade
from modules.processing.inference.frame_buffer import FrameBuffer
from modules.processing.mqtt_router import SensorMqttRouter
from modules.processing.mqtt_topics import (
    build_student_data_subscription,
    build_student_data_topic,
    build_student_result_topic,
    parse_seat_id,
)
from modules.processing.publishing import (
    SeatStatusUpdate,
    StudentSeatStatus,
    build_mqtt_publications,
)
from modules.processing.repositories.registry import InMemoryProcessingRegistry
from modules.processing.schemas import FrameMeasurements, SensorMeasurements
from modules.processing.services.frame_processing_service import (
    FrameProcessingService,
)
from tests.helpers import FakeFramePredictor, MutableTimer


class RecordingStatusPublisher:
    def __init__(self) -> None:
        self.updates: list[SeatStatusUpdate] = []

    def publish(self, update: SeatStatusUpdate) -> None:
        self.updates.append(update)


def test_sensor_message_is_validated_mapped_to_seat_and_used_by_camera_rules() -> None:
    async def run() -> None:
        processing_registry = InMemoryProcessingRegistry()
        timer = MutableTimer()
        settings = Settings(demo_seat_count=10)
        processing_service = FrameProcessingService(
            processing_registry,
            FrameBuffer(),
            FakeFramePredictor(),
            settings,
            timer=timer,
        )
        mqtt_router = SensorMqttRouter(
            settings, ProcessingFacade(processing_service), asyncio.Queue()
        )
        connection_id = uuid4()
        await processing_service.open_connection(connection_id)
        await processing_service.associate_seat(connection_id, 1)

        await mqtt_router._handle_message(
            "drowsy/student1/data",
            b'{"fsr": 1234, "tof": 420, "present": 1}',
        )
        processing_service._apply_frame_measurements(
            FrameMeasurements(
                connection_id=connection_id,
                frame_id=1,
                captured_at_ms=1792390000000,
                left_ear=0.1,
                right_ear=0.1,
            )
        )

        record = processing_registry.get(connection_id)
        assert record is not None and record.detection_state.detection is not None
        result = record.detection_state.detection
        assert result.fsr_raw == 1234
        assert result.tof_distance_mm == 420
        assert result.minute.valid_samples == 1
        assert result.minute.drowsy_samples == 1

    asyncio.run(run())


def test_firmware_sensor_topic_maps_readings_to_camera_result() -> None:
    async def run() -> None:
        processing_registry = InMemoryProcessingRegistry()
        settings = Settings(demo_seat_count=1)
        processing_service = FrameProcessingService(
            processing_registry,
            FrameBuffer(),
            FakeFramePredictor(),
            settings,
        )
        mqtt_router = SensorMqttRouter(
            settings, ProcessingFacade(processing_service), asyncio.Queue()
        )
        connection_id = uuid4()
        await processing_service.open_connection(connection_id)
        await processing_service.associate_seat(connection_id, 1)

        await mqtt_router._handle_message(
            "wakey/student1/sensors",
            b'{"tof":35,"fsr":2300,"present":1}',
        )
        processing_service._apply_frame_measurements(
            FrameMeasurements(
                connection_id=connection_id,
                frame_id=1,
                captured_at_ms=1792390000000,
                left_ear=0.1,
                right_ear=0.1,
            )
        )

        record = processing_registry.get(connection_id)
        assert record is not None and record.detection_state.detection is not None
        result = record.detection_state.detection
        assert result.fsr_raw == 2300
        assert result.tof_distance_mm == 35
        assert result.present is True
        assert result.minute.drowsy_samples == 1

    asyncio.run(run())


def test_firmware_invalid_tof_sentinel_is_treated_as_missing_distance() -> None:
    async def run() -> None:
        processing_registry = InMemoryProcessingRegistry()
        settings = Settings(demo_seat_count=1)
        processing_service = FrameProcessingService(
            processing_registry,
            FrameBuffer(),
            FakeFramePredictor(),
            settings,
        )
        mqtt_router = SensorMqttRouter(
            settings, ProcessingFacade(processing_service), asyncio.Queue()
        )
        connection_id = uuid4()
        await processing_service.open_connection(connection_id)
        await processing_service.associate_seat(connection_id, 1)

        await mqtt_router._handle_message(
            "wakey/student1/sensors",
            b'{"tof":-1,"fsr":0,"present":0}',
        )
        processing_service._apply_frame_measurements(
            FrameMeasurements(
                connection_id=connection_id,
                frame_id=1,
                captured_at_ms=1792390000000,
                left_ear=0.1,
                right_ear=0.1,
            )
        )

        record = processing_registry.get(connection_id)
        assert record is not None and record.detection_state.detection is not None
        result = record.detection_state.detection
        assert result.fsr_raw == 0
        assert result.tof_distance_mm is None
        assert result.present is False
        assert result.minute.valid_samples == 0

    asyncio.run(run())


def test_sensor_message_without_timestamp_uses_presence_for_classification() -> None:
    async def run() -> None:
        processing_registry = InMemoryProcessingRegistry()
        settings = Settings(demo_seat_count=1)
        processing_service = FrameProcessingService(
            processing_registry,
            FrameBuffer(),
            FakeFramePredictor(),
            settings,
        )
        mqtt_router = SensorMqttRouter(
            settings, ProcessingFacade(processing_service), asyncio.Queue()
        )
        connection_id = uuid4()
        await processing_service.open_connection(connection_id)
        await processing_service.associate_seat(connection_id, 1)

        await mqtt_router._handle_message(
            "drowsy/student1/data",
            b'{"fsr": 530, "tof": 129, "present": 0}',
        )
        processing_service._apply_frame_measurements(
            FrameMeasurements(
                connection_id=connection_id,
                frame_id=1,
                captured_at_ms=1792390000000,
                left_ear=0.1,
                right_ear=0.1,
            )
        )

        record = processing_registry.get(connection_id)
        assert record is not None and record.detection_state.detection is not None
        result = record.detection_state.detection
        assert result.fsr_raw == 530
        assert result.tof_distance_mm == 129
        assert result.minute.valid_samples == 0
        assert result.minute.drowsy_samples == 0

    asyncio.run(run())


def test_invalid_or_unmapped_mqtt_sensor_messages_are_ignored() -> None:
    async def run() -> None:
        processing_registry = InMemoryProcessingRegistry()
        settings = Settings(demo_seat_count=1)
        processing_service = FrameProcessingService(
            processing_registry,
            FrameBuffer(),
            FakeFramePredictor(),
            settings,
        )
        mqtt_router = SensorMqttRouter(
            settings, ProcessingFacade(processing_service), asyncio.Queue()
        )
        connection_id = uuid4()
        await processing_service.open_connection(connection_id)
        await processing_service.associate_seat(connection_id, 1)

        await mqtt_router._handle_message(
            "drowsy/student2/data",
            b'{"fsr": 1234, "tof": 420, "present": 1}',
        )
        await mqtt_router._handle_message(
            "drowsy/student1/data",
            b'{"fsr": 5000, "tof": 420, "present": 1}',
        )
        await mqtt_router._handle_message("drowsy/student1/data", b"not-json")
        processing_service._apply_frame_measurements(
            FrameMeasurements(
                connection_id=connection_id,
                frame_id=1,
                captured_at_ms=1792390000000,
                left_ear=0.1,
                right_ear=0.1,
            )
        )

        record = processing_registry.get(connection_id)
        assert record is not None and record.detection_state.detection is not None
        result = record.detection_state.detection
        assert result.fsr_raw is None and result.tof_distance_mm is None
        assert result.minute.valid_samples == 0
        assert result.minute.drowsy_samples == 0

    asyncio.run(run())


def test_expired_sensor_measurements_make_camera_drowsiness_unavailable() -> None:
    async def run() -> None:
        processing_registry = InMemoryProcessingRegistry()
        timer = MutableTimer()
        settings = Settings(demo_seat_count=1, mqtt_sensor_max_age_seconds=5.0)
        processing_service = FrameProcessingService(
            processing_registry,
            FrameBuffer(),
            FakeFramePredictor(),
            settings,
            timer=timer,
        )
        mqtt_router = SensorMqttRouter(
            settings, ProcessingFacade(processing_service), asyncio.Queue()
        )
        connection_id = uuid4()
        await processing_service.open_connection(connection_id)
        await processing_service.associate_seat(connection_id, 1)
        await mqtt_router._handle_message(
            "drowsy/student1/data",
            b'{"fsr": 0, "tof": 420, "present": 1}',
        )
        timer.current_time = 5.1
        processing_service._apply_frame_measurements(
            FrameMeasurements(
                connection_id=connection_id,
                frame_id=1,
                captured_at_ms=1792390000000,
                left_ear=0.1,
                right_ear=0.1,
            )
        )

        record = processing_registry.get(connection_id)
        assert record is not None and record.detection_state.detection is not None
        result = record.detection_state.detection
        assert result.fsr_raw is None and result.tof_distance_mm is None
        assert result.minute.valid_samples == 0
        assert result.minute.drowsy_samples == 0

    asyncio.run(run())


def _runtime(
    seat_count: int,
    publisher: RecordingStatusPublisher | None = None,
    timer: MutableTimer | None = None,
) -> tuple[FrameProcessingService, SensorMqttRouter, InMemoryProcessingRegistry]:
    processing_registry = InMemoryProcessingRegistry()
    settings = Settings(demo_seat_count=seat_count)
    processing_service = FrameProcessingService(
        processing_registry,
        FrameBuffer(),
        FakeFramePredictor(),
        settings,
        timer=timer,
        status_publisher=publisher,
    )
    mqtt_router = SensorMqttRouter(
        settings, ProcessingFacade(processing_service), asyncio.Queue()
    )
    return processing_service, mqtt_router, processing_registry


def _sensor_message(fsr: int, tof_mm: int, *, present: int = 1) -> bytes:
    return json.dumps({"fsr": fsr, "tof": tof_mm, "present": present}).encode()


def _camera_frame(
    connection_id: UUID, frame_id: int, captured_at_ms: float
) -> FrameMeasurements:
    return FrameMeasurements(
        connection_id=connection_id,
        frame_id=frame_id,
        captured_at_ms=captured_at_ms,
        left_ear=0.1,
        right_ear=0.1,
    )


def _raise_alert(
    processing_service: FrameProcessingService, connection_id: UUID
) -> None:
    for index in range(30):
        processing_service._apply_frame_measurements(
            _camera_frame(connection_id, index + 1, float(index * 1000))
        )


def test_sensor_reading_publishes_student_status_without_lecturer_notice() -> None:
    async def run() -> None:
        publisher = RecordingStatusPublisher()
        processing_service, mqtt_router, _registry = _runtime(10, publisher)
        connection_id = uuid4()
        await processing_service.open_connection(connection_id)
        await processing_service.associate_seat(connection_id, 1)

        await mqtt_router._handle_message(
            "drowsy/stud/1/data",
            _sensor_message(1234, 420),
        )

        assert publisher.updates == [
            SeatStatusUpdate(student=StudentSeatStatus(seat_id=1, drowsy=False))
        ]

    asyncio.run(run())


@pytest.mark.parametrize(("fsr", "present"), [(0, 1), (100, 0)])
def test_sensor_absence_reclassifies_latest_camera_sample(
    fsr: int, present: int
) -> None:
    async def run() -> None:
        publisher = RecordingStatusPublisher()
        timer = MutableTimer()
        processing_service, mqtt_router, registry = _runtime(1, publisher, timer)
        connection_id = uuid4()
        await processing_service.open_connection(connection_id)
        await processing_service.associate_seat(connection_id, 1)
        await mqtt_router._handle_message(
            "drowsy/stud/1/data", _sensor_message(100, 420)
        )
        processing_service._apply_frame_measurements(
            _camera_frame(connection_id, 1, 1792390000000)
        )
        publisher.updates.clear()
        timer.current_time = 1.0

        await mqtt_router._handle_message(
            "drowsy/stud/1/data",
            _sensor_message(fsr, 420, present=present),
        )

        record = registry.get(connection_id)
        assert record is not None and record.detection_state.detection is not None
        assert record.processed_frames == 1
        assert len(record.detection_state.samples) == 1
        assert record.detection_state.samples[-1].drowsy is None
        assert record.detection_state.detection.fsr_raw == fsr
        assert record.detection_state.detection.present is bool(present)
        assert publisher.updates == [
            SeatStatusUpdate(student=StudentSeatStatus(seat_id=1, drowsy=False))
        ]

    asyncio.run(run())


def test_alert_publishes_student_status_and_drowsy_seat_ids() -> None:
    async def run() -> None:
        publisher = RecordingStatusPublisher()
        processing_service, mqtt_router, _registry = _runtime(2, publisher)
        first = uuid4()
        second = uuid4()
        await processing_service.open_connection(first)
        await processing_service.associate_seat(first, 1)
        await processing_service.open_connection(second)
        await processing_service.associate_seat(second, 2)

        await mqtt_router._handle_message(
            "drowsy/stud/1/data", _sensor_message(100, 420)
        )
        await mqtt_router._handle_message(
            "drowsy/stud/2/data", _sensor_message(100, 420)
        )
        _raise_alert(processing_service, first)
        lecturer_updates = [
            update.drowsy_seats
            for update in publisher.updates
            if update.drowsy_seats is not None
        ]
        assert lecturer_updates == [(1,)]
        assert publisher.updates[-1].student == StudentSeatStatus(
            seat_id=1, drowsy=True
        )

        _raise_alert(processing_service, second)
        lecturer_updates = [
            update.drowsy_seats
            for update in publisher.updates
            if update.drowsy_seats is not None
        ]
        assert lecturer_updates == [(1,), (1, 2)]

        publisher.updates.clear()
        processing_service._apply_frame_measurements(_camera_frame(first, 31, 31000))
        assert [update.drowsy_seats for update in publisher.updates] == [None]

        await processing_service.close_connection(first)
        assert publisher.updates[-1] == SeatStatusUpdate(
            student=StudentSeatStatus(seat_id=1, drowsy=False),
            drowsy_seats=(2,),
        )

    asyncio.run(run())


def test_repeated_sensor_readings_inside_one_second_publish_once() -> None:
    async def run() -> None:
        publisher = RecordingStatusPublisher()
        timer = MutableTimer()
        processing_service, mqtt_router, registry = _runtime(1, publisher, timer)
        connection_id = uuid4()
        await processing_service.open_connection(connection_id)
        await processing_service.associate_seat(connection_id, 1)

        await mqtt_router._handle_message(
            "drowsy/stud/1/data",
            _sensor_message(100, 420),
        )
        await mqtt_router._handle_message(
            "drowsy/stud/1/data",
            _sensor_message(200, 430),
        )

        assert len(publisher.updates) == 1
        processing_service._apply_frame_measurements(
            _camera_frame(connection_id, 1, 1792390001000)
        )
        record = registry.get(connection_id)
        assert record is not None and record.detection_state.detection is not None
        assert record.detection_state.detection.fsr_raw == 200

    asyncio.run(run())


def test_invalid_sensor_topics_and_payloads_do_not_publish() -> None:
    async def run() -> None:
        publisher = RecordingStatusPublisher()
        _processing_service, mqtt_router, _registry = _runtime(1, publisher)

        await mqtt_router._handle_message(
            "drowsy/student/data",
            _sensor_message(1234, 420),
        )
        await mqtt_router._handle_message(
            "drowsy/stud/0/data",
            _sensor_message(1234, 420),
        )
        await mqtt_router._handle_message(
            "drowsy/stud/2/data",
            _sensor_message(1234, 420),
        )
        await mqtt_router._handle_message("drowsy/stud/1/data", b"not-json")
        await mqtt_router._handle_message(
            "drowsy/stud/1/data",
            b'{"fsr": 5000, "tof_mm": 420, "timestamp_ms": 1792390000000}',
        )

        assert publisher.updates == []

    asyncio.run(run())


@pytest.mark.parametrize("seat_id", [None, 1])
@pytest.mark.parametrize("error", [None, "invalid_frame"])
def test_frame_results_increment_counters_only_for_successful_frames(
    seat_id: int | None, error: str | None
) -> None:
    async def run() -> None:
        processing_service, _mqtt_router, registry = _runtime(1)
        connection_id = uuid4()
        await processing_service.open_connection(connection_id)
        if seat_id is not None:
            await processing_service.associate_seat(connection_id, seat_id)

        first = _camera_frame(connection_id, 1, 1000.0)
        second = _camera_frame(connection_id, 2, 2000.0)
        second = second.model_copy(update={"error": error})
        processing_service._apply_frame_measurements(first)
        processing_service._apply_frame_measurements(second)

        record = registry.get(connection_id)
        assert record is not None and record.detection_state.detection is not None
        expected_frames = 2 if error is None else 1
        assert record.processed_frames == expected_frames
        assert len(record.detection_state.samples) == expected_frames
        assert record.detection_state.detection.frame_id == expected_frames
        assert record.error == error

    asyncio.run(run())


@pytest.mark.parametrize("timestamp_ms", [1000.0, 2000.0])
def test_older_or_duplicate_sensor_readings_do_not_change_state_or_publish(
    timestamp_ms: float,
) -> None:
    async def run() -> None:
        publisher = RecordingStatusPublisher()
        timer = MutableTimer()
        processing_service, _mqtt_router, registry = _runtime(1, publisher, timer)
        connection_id = uuid4()
        await processing_service.open_connection(connection_id)
        await processing_service.associate_seat(connection_id, 1)
        measurements = SensorMeasurements(
            fsr_raw=100, tof_distance_mm=420, captured_at_ms=2000.0, present=True
        )
        await processing_service.submit_sensor_measurements(1, measurements)
        processing_service._apply_frame_measurements(
            _camera_frame(connection_id, 1, 2000.0)
        )
        previous_record = registry.get(connection_id)
        publisher.updates.clear()
        timer.current_time = 1.0
        outdated_measurements = measurements.model_copy(
            update={"fsr_raw": 0, "captured_at_ms": timestamp_ms}
        )

        await processing_service.submit_sensor_measurements(1, outdated_measurements)

        assert registry.get(connection_id) == previous_record
        assert publisher.updates == []

    asyncio.run(run())


def test_sensor_publish_intervals_are_per_seat_and_unaffected_by_camera_updates() -> (
    None
):
    async def run() -> None:
        publisher = RecordingStatusPublisher()
        timer = MutableTimer()
        processing_service, mqtt_router, _registry = _runtime(2, publisher, timer)
        connection_id = uuid4()
        await processing_service.open_connection(connection_id)
        await processing_service.associate_seat(connection_id, 1)
        await mqtt_router._handle_message(
            "drowsy/stud/1/data", _sensor_message(100, 420)
        )
        timer.current_time = 0.5
        await mqtt_router._handle_message(
            "drowsy/stud/2/data", _sensor_message(100, 420)
        )
        assert len(publisher.updates) == 2

        timer.current_time = 0.999
        await mqtt_router._handle_message(
            "drowsy/stud/1/data", _sensor_message(100, 420)
        )
        assert len(publisher.updates) == 2
        processing_service._apply_frame_measurements(
            _camera_frame(connection_id, 1, 2000.0)
        )
        assert len(publisher.updates) == 3

        timer.current_time = 1.0
        await mqtt_router._handle_message(
            "drowsy/stud/1/data", _sensor_message(100, 420)
        )
        assert len(publisher.updates) == 4
        timer.current_time = 1.499
        await mqtt_router._handle_message(
            "drowsy/stud/2/data", _sensor_message(100, 420)
        )
        assert len(publisher.updates) == 4
        timer.current_time = 1.5
        await mqtt_router._handle_message(
            "drowsy/stud/2/data", _sensor_message(100, 420)
        )
        assert publisher.updates == [
            SeatStatusUpdate(student=StudentSeatStatus(seat_id=seat_id, drowsy=False))
            for seat_id in (1, 2, 1, 1, 2)
        ]

    asyncio.run(run())


def test_sensor_alert_changes_bypass_throttling_and_reset_the_interval() -> None:
    async def run() -> None:
        publisher = RecordingStatusPublisher()
        timer = MutableTimer()
        processing_service, mqtt_router, _registry = _runtime(1, publisher, timer)
        connection_id = uuid4()
        await processing_service.open_connection(connection_id)
        await processing_service.associate_seat(connection_id, 1)
        await mqtt_router._handle_message(
            "drowsy/stud/1/data", _sensor_message(100, 420)
        )
        _raise_alert(processing_service, connection_id)
        publisher.updates.clear()

        timer.current_time = 0.25
        await mqtt_router._handle_message("drowsy/stud/1/data", _sensor_message(0, 420))
        cleared_alert = SeatStatusUpdate(
            student=StudentSeatStatus(seat_id=1, drowsy=False), drowsy_seats=()
        )
        assert publisher.updates == [cleared_alert]

        timer.current_time = 1.0
        await mqtt_router._handle_message("drowsy/stud/1/data", _sensor_message(0, 420))
        assert publisher.updates == [cleared_alert]
        timer.current_time = 1.25
        await mqtt_router._handle_message("drowsy/stud/1/data", _sensor_message(0, 420))
        assert publisher.updates == [
            cleared_alert,
            SeatStatusUpdate(student=StudentSeatStatus(seat_id=1, drowsy=False)),
        ]

    asyncio.run(run())


def test_topic_templates_match_the_sensor_pattern() -> None:
    topic = build_student_data_topic(12)
    result_topic = build_student_result_topic(12)
    subscription = build_student_data_subscription()
    parsed_seat_id = parse_seat_id(topic)
    assert topic == "drowsy/stud/12/data"
    assert result_topic == "drowsy/stud/12/result"
    assert subscription == "drowsy/stud/+/data"
    assert parsed_seat_id == 12
    assert parse_seat_id("drowsy/student1/data") == 1
    assert parse_seat_id("wakey/student1/sensors") == 1


def test_status_update_uses_student_and_lecturer_topics() -> None:
    update = SeatStatusUpdate(
        student=StudentSeatStatus(seat_id=1, drowsy=True),
        drowsy_seats=(1, 2),
    )
    publications = build_mqtt_publications(update)

    assert [(item.topic, item.retain) for item in publications] == [
        ("drowsy/stud/1/result", False),
        ("drowsy/lect/result", True),
    ]
    assert json.loads(publications[0].payload) == {"drowsy": True}
    assert json.loads(publications[1].payload) == {"drowsy_seats": [1, 2]}
