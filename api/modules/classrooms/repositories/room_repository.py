from typing import Protocol

from modules.classrooms.schemas import RoomInfo


class RoomRepository(Protocol):
    async def list_rooms(self) -> list[RoomInfo]: ...


class InMemoryRoomRepository:
    def __init__(self, rooms: list[RoomInfo]) -> None:
        self._rooms = rooms

    async def list_rooms(self) -> list[RoomInfo]:
        return self._rooms
