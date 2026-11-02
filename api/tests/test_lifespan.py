import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest

from core.config import Settings
from main import create_app
from modules.processing.inference import InferenceRuntime
from modules.processing.mqtt_router import SensorMqttRouter
from modules.processing.services.frame_processing_service import FrameProcessingService
from modules.streaming.router import StreamingSocketRouter
from tests.helpers import FakeFramePredictor


class RecordingLifecycle:
    def __init__(self, failure: str | None) -> None:
        self.events: list[str] = []
        self._failure = failure

    def record(self, event: str) -> None:
        self.events.append(event)
        if event == self._failure:
            raise RuntimeError(event)

    @asynccontextmanager
    async def create_inference_runtime(
        self, settings: Settings
    ) -> AsyncIterator[InferenceRuntime]:
        self.record("inference.start")
        try:
            yield InferenceRuntime(FakeFramePredictor(), 1)
        finally:
            self.record("inference.stop")

    def start_processing(self, workers: int) -> None:
        self.record("processing.start")

    def start_mqtt(self) -> None:
        self.record("mqtt.start")

    async def stop_mqtt(self) -> None:
        self.record("mqtt.stop")

    async def stop_streaming(self) -> None:
        self.record("streaming.stop")

    async def stop_processing(self) -> None:
        self.record("processing.stop")


@pytest.mark.parametrize(
    "failure",
    [
        None,
        "processing.start",
        "mqtt.start",
        "running",
        "mqtt.stop",
        "streaming.stop",
        "processing.stop",
    ],
)
def test_lifespan_attempts_all_cleanup_in_order(
    monkeypatch: pytest.MonkeyPatch, failure: str | None
) -> None:
    lifecycle = RecordingLifecycle(failure)
    monkeypatch.setattr(FrameProcessingService, "start", lifecycle.start_processing)
    monkeypatch.setattr(FrameProcessingService, "stop", lifecycle.stop_processing)
    monkeypatch.setattr(SensorMqttRouter, "start", lifecycle.start_mqtt)
    monkeypatch.setattr(SensorMqttRouter, "stop", lifecycle.stop_mqtt)
    monkeypatch.setattr(StreamingSocketRouter, "stop", lifecycle.stop_streaming)
    settings = Settings(mqtt_enabled=False)
    application = create_app(
        settings, inference_factory=lifecycle.create_inference_runtime
    )

    async def run() -> None:
        async with application.router.lifespan_context(application):
            lifecycle.record("running")

    if failure is None:
        asyncio.run(run())
    else:
        with pytest.raises(RuntimeError, match=failure):
            asyncio.run(run())

    startup_events = ["inference.start", "processing.start"]
    if failure != "processing.start":
        startup_events.append("mqtt.start")
    if failure not in {"processing.start", "mqtt.start"}:
        startup_events.append("running")
    assert lifecycle.events == [
        *startup_events,
        "mqtt.stop",
        "streaming.stop",
        "processing.stop",
        "inference.stop",
    ]
