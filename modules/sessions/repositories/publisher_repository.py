from typing import Protocol
from uuid import UUID

from modules.sessions.schemas import PublisherSession


class PublisherRepository(Protocol):
    async def get_publisher(self, connection_id: UUID) -> PublisherSession | None: ...

    async def claim_publisher(
        self, publisher: PublisherSession, limit: int
    ) -> str | None: ...

    async def release_publisher(self, connection_id: UUID) -> None: ...


class InMemoryPublisherRepository:
    def __init__(self) -> None:
        self._publishers: dict[int, PublisherSession] = {}

    async def get_publisher(self, connection_id: UUID) -> PublisherSession | None:
        for publisher in self._publishers.values():
            if publisher.connection_id == connection_id:
                return publisher
        return None

    async def claim_publisher(
        self, publisher: PublisherSession, limit: int
    ) -> str | None:
        if publisher.seat_id in self._publishers:
            return "seat_busy"
        if len(self._publishers) >= limit:
            return "capacity_reached"
        self._publishers[publisher.seat_id] = publisher
        return None

    async def release_publisher(self, connection_id: UUID) -> None:
        for seat_id, publisher in self._publishers.items():
            if publisher.connection_id == connection_id:
                del self._publishers[seat_id]
                return
