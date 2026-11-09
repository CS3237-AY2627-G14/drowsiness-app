from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from modules.processing.publishing import (
    QueueSeatStatusPublisher,
    SeatStatusUpdate,
)


class LecturerSeatStatus(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    seat_id: int
    drowsy: bool
    present: bool | None = None


class LecturerSeatSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    drowsy_seats: tuple[int, ...]
    seats: tuple[LecturerSeatStatus, ...]


router = APIRouter(prefix="/api/lecturer", tags=["lecturer"])


@router.get("/seats")
async def get_lecturer_seats(request: Request) -> LecturerSeatSnapshot:
    publisher: QueueSeatStatusPublisher | None = getattr(
        request.app.state, "status_publisher", None
    )
    if publisher is None:
        return LecturerSeatSnapshot(drowsy_seats=(), seats=())

    updates: tuple[SeatStatusUpdate, ...] = publisher.get_snapshot()
    lecturer_seats: tuple[int, ...] = ()
    for update in updates:
        if update.drowsy_seats is not None:
            lecturer_seats = update.drowsy_seats
            break
    student_updates = tuple(
        update.student for update in updates if update.student is not None
    )
    seats = tuple(
        LecturerSeatStatus(
            seat_id=student.seat_id,
            drowsy=student.drowsy,
            present=student.present,
        )
        for student in student_updates
    )
    return LecturerSeatSnapshot(
        drowsy_seats=lecturer_seats,
        seats=seats,
    )
