import asyncio
import json
from uuid import UUID, uuid4

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
from modules.processing.schemas import FrameMeasurements
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
            "drowsy/stud/1/data",
            b'{"fsr": 1234, "tof_mm": 420, "timestamp_ms": 1792390000000}',
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
            "drowsy/stud/2/data",
            b'{"fsr": 1234, "tof_mm": 420, "timestamp_ms": 1792390000000}',
        )
        await mqtt_router._handle_message(
            "drowsy/stud/1/data",
            b'{"fsr": 5000, "tof_mm": 420, "timestamp_ms": 1792390000000}',
        )
        await mqtt_router._handle_message("drowsy/stud/1/data", b"not-json")
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
        assert result.minute.drowsy_samples == 1

    asyncio.run(run())


def test_expired_sensor_measurements_do_not_change_camera_classification() -> None:
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
            "drowsy/stud/1/data",
            b'{"fsr": 0, "tof_mm": 420, "timestamp_ms": 1792390000000}',
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
        assert result.minute.drowsy_samples == 1

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


def _sensor_message(fsr: int, tof_mm: int, timestamp_ms: float) -> bytes:
    return json.dumps(
        {"fsr": fsr, "tof_mm": tof_mm, "timestamp_ms": timestamp_ms}
    ).encode()


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
            _sensor_message(1234, 420, 1792390000000),
        )

        assert publisher.updates == [
            SeatStatusUpdate(student=StudentSeatStatus(seat_id=1, drowsy=False))
        ]

    asyncio.run(run())


def test_zero_fsr_reclassifies_latest_camera_sample() -> None:
    async def run() -> None:
        publisher = RecordingStatusPublisher()
        processing_service, mqtt_router, registry = _runtime(1, publisher)
        connection_id = uuid4()
        await processing_service.open_connection(connection_id)
        await processing_service.associate_seat(connection_id, 1)
        processing_service._apply_frame_measurements(
            _camera_frame(connection_id, 1, 1792390000000)
        )
        publisher.updates.clear()

        await mqtt_router._handle_message(
            "drowsy/stud/1/data",
            _sensor_message(0, 420, 1792390001000),
        )

        record = registry.get(connection_id)
        assert record is not None and record.detection_state.detection is not None
        assert record.detection_state.samples[-1].drowsy is None
        assert record.detection_state.detection.fsr_raw == 0
        assert publisher.updates == [
            SeatStatusUpdate(student=StudentSeatStatus(seat_id=1, drowsy=False))
        ]

    asyncio.run(run())


def test_alert_publishes_student_status_and_drowsy_seat_ids() -> None:
    async def run() -> None:
        publisher = RecordingStatusPublisher()
        processing_service, _mqtt_router, _registry = _runtime(2, publisher)
        first = uuid4()
        second = uuid4()
        await processing_service.open_connection(first)
        await processing_service.associate_seat(first, 1)
        await processing_service.open_connection(second)
        await processing_service.associate_seat(second, 2)

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
            _sensor_message(100, 420, 1792390000000),
        )
        await mqtt_router._handle_message(
            "drowsy/stud/1/data",
            _sensor_message(200, 430, 1792390001000),
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
            _sensor_message(1234, 420, 1792390000000),
        )
        await mqtt_router._handle_message(
            "drowsy/student1/data",
            _sensor_message(1234, 420, 1792390000000),
        )
        await mqtt_router._handle_message(
            "drowsy/stud/2/data",
            _sensor_message(1234, 420, 1792390000000),
        )
        await mqtt_router._handle_message("drowsy/stud/1/data", b"not-json")
        await mqtt_router._handle_message(
            "drowsy/stud/1/data",
            b'{"fsr": 5000, "tof_mm": 420, "timestamp_ms": 1792390000000}',
        )

        assert publisher.updates == []

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
    assert parse_seat_id("drowsy/student1/data") is None


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
