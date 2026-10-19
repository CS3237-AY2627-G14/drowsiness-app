from typing import Protocol

from modules.classrooms.schemas import SeatInfo


class SeatRepository(Protocol):
    async def list_seats(self, room_id: int) -> list[SeatInfo]: ...

    async def get_seat(self, seat_id: int) -> SeatInfo | None: ...


class InMemorySeatRepository:
    def __init__(self, seats: list[SeatInfo]) -> None:
        self._seats = {seat.id: seat for seat in seats}

    async def list_seats(self, room_id: int) -> list[SeatInfo]:
        return [seat for seat in self._seats.values() if seat.room_id == room_id]

    async def get_seat(self, seat_id: int) -> SeatInfo | None:
        return self._seats.get(seat_id)
