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
        mqtt_router = SensorMqttRouter(settings, ProcessingFacade(processing_service))
        connection_id = uuid4()
        await processing_service.open_connection(connection_id)
        await processing_service.associate_seat(connection_id, 1)

        await mqtt_router._handle_message(
            "drowsy/student2/data",
            b'{"fsr": 1234, "tof_mm": 420, "timestamp_ms": 1792390000000}',
        )
        await mqtt_router._handle_message(
            "drowsy/student1/data",
            b'{"fsr": 5000, "tof_mm": 420, "timestamp_ms": 1792390000000}',
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
        mqtt_router = SensorMqttRouter(settings, ProcessingFacade(processing_service))
        connection_id = uuid4()
        await processing_service.open_connection(connection_id)
        await processing_service.associate_seat(connection_id, 1)
        await mqtt_router._handle_message(
            "drowsy/student1/data",
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
