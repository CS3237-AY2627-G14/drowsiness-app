import asyncio
import time
from typing import Self
from uuid import uuid4

import pytest

from core.config import Settings
from modules.processing.inference.frame_buffer import FrameBuffer
from modules.processing.mqtt_result_publisher import MqttResultPublisher
from modules.processing.repositories.registry import InMemoryProcessingRegistry
from modules.processing.schemas import FrameMeasurements
from modules.processing.services.frame_processing_service import (
    FrameProcessingService,
)
from tests.helpers import FakeFramePredictor


def test_result_publishes_aggregate_and_per_student_topics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> list[tuple[str, bytes, int]]:
        published: list[tuple[str, bytes, int]] = []
        complete = asyncio.get_running_loop().create_future()

        class FakeMqttClient:
            def __init__(self, *, hostname: str, port: int) -> None:
                assert hostname == "127.0.0.1"
                assert port == 1883

            async def __aenter__(self) -> Self:
                return self

            async def __aexit__(self, *args: object) -> None:
                return None

            async def publish(self, topic: str, payload: bytes, *, qos: int) -> None:
                published.append((topic, payload, qos))
                if len(published) == 6:
                    complete.set_result(None)

        monkeypatch.setattr(
            "modules.processing.mqtt_result_publisher.aiomqtt.Client",
            FakeMqttClient,
        )
        publisher = MqttResultPublisher(Settings(demo_seat_count=1))
        publisher.start()
        publisher.enqueue_result((1, 2))
        publisher.enqueue_result(())
        await asyncio.wait_for(complete, timeout=1)
        published_at_ms = publisher.last_published_at_ms
        await publisher.stop()
        assert published_at_ms is not None
        return published

    assert asyncio.run(run()) == [
        ("drowsy/result", b'{"drowsy_seats": ["A1", "A2"], "total_drowsy": 2}', 1),
        ("drowsy/A1/result", b'{"drowsy": true}', 1),
        ("drowsy/A2/result", b'{"drowsy": true}', 1),
        ("drowsy/result", b'{"drowsy_seats": [], "total_drowsy": 0}', 1),
        ("drowsy/A1/result", b'{"drowsy": false}', 1),
        ("drowsy/A2/result", b'{"drowsy": false}', 1),
    ]


def test_alert_publishes_once_when_alert_turns_on() -> None:
    class FakeResultPublisher:
        def __init__(self) -> None:
            self.alert_count = 0
            self.last_published_at_ms = time.time_ns() / 1_000_000

        def enqueue_result(self, drowsy_seat_ids: tuple[int, ...]) -> None:
            self.alert_count += 1

    async def run() -> tuple[int, bool]:
        result_publisher = FakeResultPublisher()
        processing_service = FrameProcessingService(
            InMemoryProcessingRegistry(),
            FrameBuffer(),
            FakeFramePredictor(),
            Settings(demo_seat_count=1),
            mqtt_result_publisher=result_publisher,
        )
        connection_id = uuid4()
        await processing_service.open_connection(connection_id)
        await processing_service.associate_seat(connection_id, 1)

        for frame_id in range(1, 32):
            processing_service._apply_frame_measurements(
                FrameMeasurements(
                    connection_id=connection_id,
                    frame_id=frame_id,
                    captured_at_ms=1_792_390_000_000 + frame_id * 1000,
                    left_ear=0.1,
                    right_ear=0.1,
                    sensor_drowsy=True,
                    present=True,
                )
            )
        status = await processing_service.get_status(connection_id)
        return result_publisher.alert_count, status.mqtt_alert_sent_recently

    assert asyncio.run(run()) == (1, True)
