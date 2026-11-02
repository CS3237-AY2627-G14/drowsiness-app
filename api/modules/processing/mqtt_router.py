import asyncio
import logging

import aiomqtt
from pydantic import ValidationError

from core.config import Settings
from modules.processing.facade import ProcessingFacade, RawTelemetry
from modules.processing.mqtt_topics import (
    STUDENT_DATA_SUBSCRIPTIONS,
    parse_seat_id,
)
from modules.processing.publishing import (
    QueueSeatStatusPublisher,
    SeatStatusUpdate,
    build_mqtt_publications,
)

logger = logging.getLogger(__name__)


class SensorMqttRouter:
    def __init__(
        self,
        settings: Settings,
        processing_facade: ProcessingFacade,
        status_updates: asyncio.Queue[SeatStatusUpdate],
        status_publisher: QueueSeatStatusPublisher | None = None,
    ) -> None:
        self._settings = settings
        self._processing_facade = processing_facade
        self._status_updates = status_updates
        self._status_publisher = status_publisher
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if not self._settings.mqtt_enabled or self._task is not None:
            return
        self._task = asyncio.create_task(self._subscribe(), name="mqtt-sensor-client")
        self._task.add_done_callback(self._handle_task_completion)

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        await asyncio.gather(self._task, return_exceptions=True)
        self._task = None

    def _handle_task_completion(self, task: asyncio.Task[None]) -> None:
        if task.cancelled():
            return
        failure = task.exception()
        if failure is not None:
            logger.error(
                "MQTT sensor subscriber stopped unexpectedly", exc_info=failure
            )

    async def _subscribe(self) -> None:
        while True:
            try:
                async with aiomqtt.Client(
                    hostname=self._settings.mqtt_host,
                    port=self._settings.mqtt_port,
                ) as mqtt_client:
                    for subscription in STUDENT_DATA_SUBSCRIPTIONS:
                        await mqtt_client.subscribe(subscription)
                    async with asyncio.TaskGroup() as task_group:
                        task_group.create_task(self._receive_messages(mqtt_client))
                        task_group.create_task(self._publish_updates(mqtt_client))
            except* aiomqtt.MqttError as error_group:
                error = error_group.exceptions[0]
                logger.warning(
                    "MQTT connection failed for %s:%d: %s; retrying in 5 seconds",
                    self._settings.mqtt_host,
                    self._settings.mqtt_port,
                    error,
                )
                await asyncio.sleep(5)

    async def _receive_messages(self, mqtt_client: aiomqtt.Client) -> None:
        async for message in mqtt_client.messages:
            await self._handle_message(message.topic.value, message.payload)

    async def _publish_updates(self, mqtt_client: aiomqtt.Client) -> None:
        if self._status_publisher is not None:
            while not self._status_updates.empty():
                self._status_updates.get_nowait()
            for update in self._status_publisher.get_snapshot():
                await self._publish_update(mqtt_client, update)
        while True:
            update = await self._status_updates.get()
            students = {}
            lecturer_seats = update.drowsy_seats
            if update.student is not None:
                students[update.student.seat_id] = update.student
            while not self._status_updates.empty():
                update = self._status_updates.get_nowait()
                if update.student is not None:
                    students[update.student.seat_id] = update.student
                if update.drowsy_seats is not None:
                    lecturer_seats = update.drowsy_seats
            for student in students.values():
                await self._publish_update(
                    mqtt_client, SeatStatusUpdate(student=student)
                )
            if lecturer_seats is not None:
                await self._publish_update(
                    mqtt_client, SeatStatusUpdate(drowsy_seats=lecturer_seats)
                )

    async def _publish_update(
        self, mqtt_client: aiomqtt.Client, update: SeatStatusUpdate
    ) -> None:
        for publication in build_mqtt_publications(update):
            await mqtt_client.publish(
                publication.topic, publication.payload, qos=1, retain=publication.retain
            )
        if update.student is not None and self._status_publisher is not None:
            self._status_publisher.record_publication(update.student)

    async def _handle_message(self, topic: str, payload: bytes) -> None:
        seat_id = parse_seat_id(topic)
        if seat_id is None:
            return
        if seat_id > self._settings.demo_seat_count:
            logger.warning(
                "Ignoring MQTT message for unknown student seat_id=%d", seat_id
            )
            return
        if len(payload) > 1024:
            logger.warning("Ignoring oversized MQTT sensor message seat_id=%d", seat_id)
            return
        try:
            telemetry = RawTelemetry.model_validate_json(payload)
        except ValidationError:
            logger.warning("Ignoring invalid raw telemetry seat_id=%d", seat_id)
            return
        await self._processing_facade.submit_raw_telemetry(telemetry, seat_id)
