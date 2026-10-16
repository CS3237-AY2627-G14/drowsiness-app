from modules.classrooms.repositories.room_repository import RoomRepository
from modules.classrooms.repositories.seat_repository import SeatRepository
from modules.classrooms.schemas import ClassroomInfo, RoomInfo, SeatInfo


class ClassroomsService:
    """Retrieve rooms, seats and classroom layouts."""

    def __init__(
        self, room_repository: RoomRepository, seat_repository: SeatRepository
    ) -> None:
        self._room_repository = room_repository
        self._seat_repository = seat_repository

    async def list_rooms(self) -> list[RoomInfo]:
        return await self._room_repository.list_rooms()

    async def list_seats(self, room_id: int) -> list[SeatInfo]:
        return await self._seat_repository.list_seats(room_id)

    async def get_seat(self, seat_id: int) -> SeatInfo | None:
        return await self._seat_repository.get_seat(seat_id)

    async def list_classrooms(self) -> list[ClassroomInfo]:
        rooms = await self._room_repository.list_rooms()
        classrooms: list[ClassroomInfo] = []
        for room in rooms:
            seats = await self._seat_repository.list_seats(room.id)
            classroom = ClassroomInfo(id=room.id, name=room.name, seats=seats)
            classrooms.append(classroom)
        return classrooms
