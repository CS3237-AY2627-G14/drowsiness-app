import asyncio
from uuid import uuid4

from core.config import Settings
from modules.processing.facade import ProcessingFacade
from modules.processing.inference.frame_buffer import FrameBuffer
from modules.processing.mqtt_router import SensorMqttRouter
from modules.processing.repositories.registry import InMemoryProcessingRegistry
from modules.processing.schemas import FrameMeasurements
from modules.processing.services.frame_processing_service import (
    FrameProcessingService,
)
from tests.helpers import FakeFramePredictor, MutableTimer


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
        mqtt_router = SensorMqttRouter(settings, ProcessingFacade(processing_service))
        connection_id = uuid4()
        await processing_service.open_connection(connection_id)
        await processing_service.associate_seat(connection_id, 1)

        await mqtt_router._handle_message(
            "drowsy/student1/data",
            b'{"drowsy": 1, "present": 1}',
        )
        processing_service._apply_frame_measurements(
            FrameMeasurements(
                connection_id=connection_id,
                frame_id=1,
                captured_at_ms=1792390000000,
                left_ear=0.1,
                right_ear=0.1,
                fatigue_probability=0.9,
            )
        )

        record = processing_registry.get(connection_id)
        assert record is not None and record.detection_state.detection is not None
        result = record.detection_state.detection
        assert result.sensor_drowsy is True
        assert result.present is True
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
        mqtt_router = SensorMqttRouter(settings, ProcessingFacade(processing_service))
        connection_id = uuid4()
        await processing_service.open_connection(connection_id)
        await processing_service.associate_seat(connection_id, 1)

        await mqtt_router._handle_message(
            "wakey/student1/sensors",
            b'{"drowsy":1,"present":1}',
        )
        processing_service._apply_frame_measurements(
            FrameMeasurements(
                connection_id=connection_id,
                frame_id=1,
                captured_at_ms=1792390000000,
                left_ear=0.1,
                right_ear=0.1,
                fatigue_probability=0.9,
            )
        )

        record = processing_registry.get(connection_id)
        assert record is not None and record.detection_state.detection is not None
        result = record.detection_state.detection
        assert result.sensor_drowsy is True
        assert result.present is True
        assert result.minute.drowsy_samples == 1

    asyncio.run(run())


def test_unoccupied_firmware_sensor_sample_is_not_counted() -> None:
    async def run() -> None:
        processing_registry = InMemoryProcessingRegistry()
        settings = Settings(demo_seat_count=1)
        processing_service = FrameProcessingService(
            processing_registry,
            FrameBuffer(),
            FakeFramePredictor(),
            settings,
        )
        mqtt_router = SensorMqttRouter(settings, ProcessingFacade(processing_service))
        connection_id = uuid4()
        await processing_service.open_connection(connection_id)
        await processing_service.associate_seat(connection_id, 1)

        await mqtt_router._handle_message(
            "wakey/student1/sensors",
            b'{"drowsy":1,"present":0}',
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
        assert result.sensor_drowsy is True
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
        mqtt_router = SensorMqttRouter(settings, ProcessingFacade(processing_service))
        connection_id = uuid4()
        await processing_service.open_connection(connection_id)
        await processing_service.associate_seat(connection_id, 1)

        await mqtt_router._handle_message(
            "drowsy/student1/data",
            b'{"drowsy": 1, "present": 0}',
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
        assert result.sensor_drowsy is True
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
        mqtt_router = SensorMqttRouter(settings, ProcessingFacade(processing_service))
        connection_id = uuid4()
        await processing_service.open_connection(connection_id)
        await processing_service.associate_seat(connection_id, 1)

        await mqtt_router._handle_message(
            "drowsy/student2/data",
            b'{"drowsy": 1, "present": 1}',
        )
        await mqtt_router._handle_message(
            "drowsy/student1/data",
            b'{"drowsy": 2, "present": 1}',
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
        assert result.sensor_drowsy is None and result.present is None
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
        mqtt_router = SensorMqttRouter(settings, ProcessingFacade(processing_service))
        connection_id = uuid4()
        await processing_service.open_connection(connection_id)
        await processing_service.associate_seat(connection_id, 1)
        await mqtt_router._handle_message(
            "drowsy/student1/data",
            b'{"drowsy": 1, "present": 1}',
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
        assert result.sensor_drowsy is None and result.present is None
        assert result.minute.valid_samples == 0
        assert result.minute.drowsy_samples == 0

    asyncio.run(run())
