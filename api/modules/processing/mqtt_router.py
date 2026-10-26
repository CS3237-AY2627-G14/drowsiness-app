import asyncio
import json
import logging

import aiomqtt
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from core.config import Settings
from modules.processing.facade import ProcessingFacade, SensorMeasurements
from modules.processing.mqtt_topics import (
    build_student_data_subscription,
    parse_seat_id,
)
from modules.processing.publishing import SeatStatusUpdate, build_mqtt_publications

logger = logging.getLogger(__name__)


class MqttSensorPayload(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    fsr: int = Field(ge=0, le=4095)
    tof_mm: int = Field(gt=0)
    timestamp_ms: float = Field(gt=0)


class SensorMqttRouter:
    def __init__(
        self,
        settings: Settings,
        processing_facade: ProcessingFacade,
        status_updates: asyncio.Queue[SeatStatusUpdate],
    ) -> None:
        self._settings = settings
        self._processing_facade = processing_facade
        self._status_updates = status_updates
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
                    subscription = build_student_data_subscription()
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
        while True:
            update = await self._status_updates.get()
            publications = build_mqtt_publications(update)
            for publication in publications:
                await mqtt_client.publish(
                    publication.topic,
                    publication.payload,
                    qos=0,
                    retain=publication.retain,
                )

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
            payload_data = json.loads(payload)
        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.warning("Ignoring invalid MQTT JSON payload seat_id=%d", seat_id)
            return
        try:
            sensor_payload = MqttSensorPayload.model_validate(payload_data)
        except ValidationError:
            logger.warning("Ignoring invalid MQTT sensor fields seat_id=%d", seat_id)
            return
        measurements = SensorMeasurements(
            fsr_raw=sensor_payload.fsr,
            tof_distance_mm=sensor_payload.tof_mm,
            captured_at_ms=sensor_payload.timestamp_ms,
        )
        await self._processing_facade.submit_sensor_measurements(seat_id, measurements)
