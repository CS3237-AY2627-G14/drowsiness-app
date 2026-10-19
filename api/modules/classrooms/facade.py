from modules.classrooms.schemas import ClassroomInfo, RoomInfo, SeatInfo
from modules.classrooms.service import ClassroomsService

__all__ = ["ClassroomInfo", "ClassroomsFacade", "RoomInfo", "SeatInfo"]


class ClassroomsFacade:
    def __init__(self, classrooms_service: ClassroomsService) -> None:
        self._classrooms_service = classrooms_service

    async def list_rooms(self) -> list[RoomInfo]:
        return await self._classrooms_service.list_rooms()

    async def list_seats(self, room_id: int) -> list[SeatInfo]:
        return await self._classrooms_service.list_seats(room_id)

    async def get_seat(self, seat_id: int) -> SeatInfo | None:
        return await self._classrooms_service.get_seat(seat_id)

    async def list_classrooms(self) -> list[ClassroomInfo]:
        return await self._classrooms_service.list_classrooms()
