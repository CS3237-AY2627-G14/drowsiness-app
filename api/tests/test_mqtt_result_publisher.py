import asyncio
from types import SimpleNamespace

from starlette.requests import Request

from modules.processing.publishing import (
    QueueSeatStatusPublisher,
    SeatStatusUpdate,
    StudentSeatStatus,
    build_mqtt_publications,
)
from modules.processing.router import LecturerSeatStatus, get_lecturer_seats


def test_publication_indicator_is_seat_specific() -> None:
    publisher = QueueSeatStatusPublisher(asyncio.Queue())
    assert publisher.get_last_alert_published_at(1) is None
    publisher.record_publication(StudentSeatStatus(seat_id=1, drowsy=True))
    assert publisher.get_last_alert_published_at(1) is not None
    assert publisher.get_last_alert_published_at(2) is None


def test_snapshot_retains_latest_status_and_lecturer_list() -> None:
    publisher = QueueSeatStatusPublisher(asyncio.Queue())
    publisher.publish(
        SeatStatusUpdate(
            student=StudentSeatStatus(seat_id=1, drowsy=True), drowsy_seats=(1,)
        )
    )
    publisher.publish(
        SeatStatusUpdate(
            student=StudentSeatStatus(seat_id=1, drowsy=False), drowsy_seats=()
        )
    )
    snapshot = publisher.get_snapshot()
    assert snapshot[0].drowsy_seats == ()
    assert snapshot[1].student == StudentSeatStatus(seat_id=1, drowsy=False)


def test_clearing_student_removes_seat_status_from_snapshot() -> None:
    publisher = QueueSeatStatusPublisher(asyncio.Queue())
    publisher.publish(
        SeatStatusUpdate(student=StudentSeatStatus(seat_id=1, drowsy=False))
    )
    assert len(publisher.get_snapshot()) == 2

    publisher.clear_student(1)

    snapshot = publisher.get_snapshot()
    assert snapshot == (SeatStatusUpdate(drowsy_seats=()),)


def test_lecturer_snapshot_includes_sensor_presence() -> None:
    publisher = QueueSeatStatusPublisher(asyncio.Queue())
    publisher.publish(
        SeatStatusUpdate(
            student=StudentSeatStatus(seat_id=1, drowsy=False, present=False)
        )
    )
    request = Request(
        {
            "type": "http",
            "app": SimpleNamespace(state=SimpleNamespace(status_publisher=publisher)),
        }
    )

    snapshot = asyncio.run(get_lecturer_seats(request))

    assert snapshot.seats == (
        LecturerSeatStatus(seat_id=1, drowsy=False, present=False),
    )


def test_student_mqtt_result_does_not_expose_classroom_presence_field() -> None:
    update = SeatStatusUpdate(
        student=StudentSeatStatus(seat_id=1, drowsy=False, present=False)
    )

    publication = build_mqtt_publications(update)[0]

    assert publication.payload == '{"drowsy":false}'
