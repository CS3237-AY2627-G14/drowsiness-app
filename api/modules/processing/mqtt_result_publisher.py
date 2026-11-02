import asyncio
import json
import logging
import time
from typing import Protocol

import aiomqtt

from core.config import Settings

logger = logging.getLogger(__name__)


class MqttResultPublisherPort(Protocol):
    @property
    def last_published_at_ms(self) -> float | None: ...

    def enqueue_result(self, drowsy_seat_ids: tuple[int, ...]) -> None: ...


class MqttResultPublisher:
    _topic = "drowsy/result"
    _seat_labels_by_id = {1: "A1", 2: "A2"}

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._pending_results: asyncio.Queue[tuple[str, bytes]] = asyncio.Queue(
            maxsize=100
        )
        self._task: asyncio.Task[None] | None = None
        self._last_published_at_ms: float | None = None
        self._last_drowsy_seat_ids: tuple[int, ...] = ()

    @property
    def last_published_at_ms(self) -> float | None:
        return self._last_published_at_ms

    def start(self) -> None:
        if not self._settings.mqtt_enabled or self._task is not None:
            return
        self._task = asyncio.create_task(
            self._publish_results(), name="mqtt-result-publisher"
        )
        self._task.add_done_callback(self._handle_task_completion)

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        await asyncio.gather(self._task, return_exceptions=True)
        self._task = None

    def enqueue_result(self, drowsy_seat_ids: tuple[int, ...]) -> None:
        if not self._settings.mqtt_enabled:
            return
        if self._task is None:
            logger.error("Cannot enqueue MQTT result because publisher is not running")
            return

        current_seats = tuple(
            sorted(set(drowsy_seat_ids).intersection(self._seat_labels_by_id))
        )
        drowsy_labels = [self._seat_labels_by_id[seat_id] for seat_id in current_seats]
        aggregate_payload = json.dumps(
            {
                "drowsy_seats": drowsy_labels,
                "total_drowsy": len(drowsy_labels),
            }
        ).encode("utf-8")
        affected_seats = sorted(set(self._last_drowsy_seat_ids) | set(current_seats))

        publications = [(self._topic, aggregate_payload)]
        for seat_id in affected_seats:
            seat_label = self._seat_labels_by_id[seat_id]
            student_payload = json.dumps({"drowsy": seat_id in current_seats}).encode(
                "utf-8"
            )
            publications.append((f"drowsy/{seat_label}/result", student_payload))

        try:
            for topic, payload in publications:
                self._pending_results.put_nowait((topic, payload))
            self._last_drowsy_seat_ids = current_seats
        except asyncio.QueueFull:
            logger.error("Dropping MQTT result because the pending queue is full")

    def _handle_task_completion(self, task: asyncio.Task[None]) -> None:
        if task.cancelled():
            return
        failure = task.exception()
        if failure is not None:
            logger.error("MQTT result publisher stopped unexpectedly", exc_info=failure)

    async def _publish_results(self) -> None:
        pending_result: tuple[str, bytes] | None = None
        while True:
            try:
                async with aiomqtt.Client(
                    hostname=self._settings.mqtt_host,
                    port=self._settings.mqtt_port,
                ) as mqtt_client:
                    while True:
                        if pending_result is None:
                            pending_result = await self._pending_results.get()
                        topic, payload = pending_result
                        await mqtt_client.publish(topic, payload, qos=1)
                        self._last_published_at_ms = time.time_ns() / 1_000_000
                        self._pending_results.task_done()
                        pending_result = None
            except aiomqtt.MqttError as error:
                logger.warning(
                    "MQTT result publishing failed for %s:%d: %s; "
                    "retrying in 5 seconds",
                    self._settings.mqtt_host,
                    self._settings.mqtt_port,
                    error,
                )
                await asyncio.sleep(5)
