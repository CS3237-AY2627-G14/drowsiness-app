import asyncio
import json
import logging
import re

import aiomqtt
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from core.config import Settings
from modules.processing.facade import ProcessingFacade, SensorMeasurements

logger = logging.getLogger(__name__)
SENSOR_TOPIC_PATTERN = re.compile(r"drowsy/student([1-9]\d*)/data")


class MqttSensorPayload(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    fsr: int = Field(ge=0, le=4095)
    tof_mm: int = Field(gt=0)
    timestamp_ms: float = Field(gt=0, allow_inf_nan=False)


class SensorMqttRouter:
    def __init__(self, settings: Settings, processing_facade: ProcessingFacade) -> None:
        self._settings = settings
        self._processing_facade = processing_facade
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
                    await mqtt_client.subscribe("drowsy/+/data")
                    async for message in mqtt_client.messages:
                        await self._handle_message(message.topic.value, message.payload)
            except aiomqtt.MqttError as error:
                logger.warning(
                    "MQTT connection failed for %s:%d: %s; retrying in 5 seconds",
                    self._settings.mqtt_host,
                    self._settings.mqtt_port,
                    error,
                )
                await asyncio.sleep(5)

    async def _handle_message(self, topic: str, payload: bytes) -> None:
        topic_match = SENSOR_TOPIC_PATTERN.fullmatch(topic)
        if topic_match is None:
            logger.warning("Ignoring MQTT message on unsupported topic")
            return
        seat_id = int(topic_match.group(1))
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
