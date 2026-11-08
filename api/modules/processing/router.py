from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from modules.processing.publishing import (
    QueueSeatStatusPublisher,
    SeatStatusUpdate,
    StudentSeatStatus,
)


class LecturerSeatStatus(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    seat_id: int
    drowsy: bool


class LecturerSeatSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    drowsy_seats: tuple[int, ...]
    seats: tuple[LecturerSeatStatus, ...]


class DemoSeatStatus(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    seat_id: int
    drowsy: bool


class DemoLecturerStatus(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    seats: tuple[DemoSeatStatus, ...]


router = APIRouter(prefix="/api/lecturer", tags=["lecturer"])


@router.post("/demo/statuses")
async def set_demo_statuses(
    request: Request, demo_statuses: DemoLecturerStatus
) -> LecturerSeatSnapshot:
    publisher: QueueSeatStatusPublisher | None = getattr(
        request.app.state, "status_publisher", None
    )
    if publisher is None:
        return LecturerSeatSnapshot(drowsy_seats=(), seats=())

    for seat_status in demo_statuses.seats:
        publisher.publish(
            SeatStatusUpdate(
                student=StudentSeatStatus(
                    seat_id=seat_status.seat_id,
                    drowsy=seat_status.drowsy,
                )
            )
        )
    drowsy_seats = tuple(
            sorted(
                seat_status.seat_id
                for seat_status in demo_statuses.seats
                if seat_status.drowsy
            )
        )
    publisher.publish(SeatStatusUpdate(drowsy_seats=drowsy_seats))
    return await get_lecturer_seats(request)


@router.get("/seats")
async def get_lecturer_seats(request: Request) -> LecturerSeatSnapshot:
    publisher: QueueSeatStatusPublisher | None = getattr(
        request.app.state, "status_publisher", None
    )
    if publisher is None:
        return LecturerSeatSnapshot(drowsy_seats=(), seats=())

    updates: tuple[SeatStatusUpdate, ...] = publisher.get_snapshot()
    lecturer_update = next(
        (update for update in updates if update.drowsy_seats is not None),
        None,
    )
    student_updates = tuple(
        update.student for update in updates if update.student is not None
    )
    seats = tuple(
        LecturerSeatStatus(seat_id=student.seat_id, drowsy=student.drowsy)
        for student in student_updates
    )
    return LecturerSeatSnapshot(
        drowsy_seats=lecturer_update.drowsy_seats if lecturer_update else (),
        seats=seats,
    )
