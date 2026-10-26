import asyncio
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from modules.processing.mqtt_topics import (
    LECTURER_RESULT_TOPIC,
    build_student_result_topic,
)


class StudentSeatStatus(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    seat_id: int = Field(exclude=True)
    drowsy: bool


class LecturerResult(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    drowsy_seats: tuple[int, ...]


class SeatStatusUpdate(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    student: StudentSeatStatus | None = None
    drowsy_seats: tuple[int, ...] | None = None


class MqttPublication(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    topic: str
    payload: str
    retain: bool


class SeatStatusPublisher(Protocol):
    def publish(self, update: SeatStatusUpdate) -> None: ...


class QueueSeatStatusPublisher:
    def __init__(self, updates: asyncio.Queue[SeatStatusUpdate]) -> None:
        self._updates = updates

    def publish(self, update: SeatStatusUpdate) -> None:
        self._updates.put_nowait(update)


def build_mqtt_publications(
    update: SeatStatusUpdate,
) -> tuple[MqttPublication, ...]:
    messages: list[MqttPublication] = []
    student = update.student
    if student is not None:
        topic = build_student_result_topic(student.seat_id)
        payload = student.model_dump_json()
        publication = MqttPublication(topic=topic, payload=payload, retain=False)
        messages.append(publication)
    if update.drowsy_seats is not None:
        lecturer_result = LecturerResult(drowsy_seats=update.drowsy_seats)
        payload = lecturer_result.model_dump_json()
        publication = MqttPublication(
            topic=LECTURER_RESULT_TOPIC,
            payload=payload,
            retain=True,
        )
        messages.append(publication)
    return tuple(messages)
