import asyncio

from modules.processing.publishing import QueueSeatStatusPublisher, StudentSeatStatus


def test_publication_indicator_is_seat_specific() -> None:
    publisher = QueueSeatStatusPublisher(asyncio.Queue())
    assert publisher.get_last_alert_published_at(1) is None
    publisher.record_publication(StudentSeatStatus(seat_id=1, drowsy=True))
    assert publisher.get_last_alert_published_at(1) is not None
    assert publisher.get_last_alert_published_at(2) is None


def test_snapshot_retains_latest_status_and_lecturer_list() -> None:
    from modules.processing.publishing import SeatStatusUpdate

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
    from modules.processing.publishing import SeatStatusUpdate

    publisher = QueueSeatStatusPublisher(asyncio.Queue())
    publisher.publish(
        SeatStatusUpdate(student=StudentSeatStatus(seat_id=1, drowsy=False))
    )
    assert len(publisher.get_snapshot()) == 2

    publisher.clear_student(1)

    snapshot = publisher.get_snapshot()
    assert snapshot == (SeatStatusUpdate(drowsy_seats=()),)
