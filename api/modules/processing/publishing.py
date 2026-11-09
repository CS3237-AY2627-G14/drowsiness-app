import asyncio
import time
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from modules.processing.mqtt_topics import (
    LECTURER_RESULT_TOPIC,
    build_student_result_topic,
)


class StudentSeatStatus(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    seat_id: str = Field(exclude=True)
    drowsy: bool


class LecturerResult(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    drowsy_seats: tuple[str, ...]


class SeatStatusUpdate(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    student: StudentSeatStatus | None = None
    drowsy_seats: tuple[str, ...] | None = None


class MqttPublication(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    topic: str
    payload: str
    retain: bool


class SeatStatusPublisher(Protocol):
    def publish(self, update: SeatStatusUpdate) -> None: ...

    def get_last_alert_published_at(self, seat_id: str) -> float | None: ...


class QueueSeatStatusPublisher:
    def __init__(self, updates: asyncio.Queue[SeatStatusUpdate]) -> None:
        self._updates = updates
        self._last_alert_published_at: dict[str, float] = {}
        self._students: dict[str, StudentSeatStatus] = {}
        self._drowsy_seats: tuple[str, ...] = ()

    def get_last_alert_published_at(self, seat_id: str) -> float | None:
        return self._last_alert_published_at.get(seat_id)

    def record_publication(self, student: StudentSeatStatus) -> None:
        if student.drowsy:
            self._last_alert_published_at[student.seat_id] = time.time_ns() / 1_000_000

    def get_snapshot(self) -> tuple[SeatStatusUpdate, ...]:
        return (
            SeatStatusUpdate(drowsy_seats=self._drowsy_seats),
            *(SeatStatusUpdate(student=student) for student in self._students.values()),
        )

    def publish(self, update: SeatStatusUpdate) -> None:
        if update.student is not None:
            self._students[update.student.seat_id] = update.student
        if update.drowsy_seats is not None:
            self._drowsy_seats = update.drowsy_seats
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
