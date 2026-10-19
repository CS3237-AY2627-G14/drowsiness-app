from modules.classrooms.schemas import RoomInfo, SeatInfo


def create_demo_classroom(
    seat_count: int = 10,
) -> tuple[list[RoomInfo], list[SeatInfo]]:
    rooms = [RoomInfo(id=101, name="Room 101")]
    seats = [
        SeatInfo(id=number, room_id=101, seat_number=number)
        for number in range(1, seat_count + 1)
    ]
    return rooms, seats
