from uuid import UUID

from modules.sessions.exceptions import SessionAccessException
from modules.sessions.schemas import PublisherSession
from modules.sessions.service import SessionsService

__all__ = ["PublisherSession", "SessionAccessException", "SessionsFacade"]


class SessionsFacade:
    def __init__(self, sessions_service: SessionsService) -> None:
        self._sessions_service = sessions_service

    async def open_publisher(self, *, token: str, seat_id: int) -> PublisherSession:
        return await self._sessions_service.open_publisher(token=token, seat_id=seat_id)

    async def close_publisher(self, connection_id: UUID) -> None:
        await self._sessions_service.close_publisher(connection_id)

    async def validate_publisher(self, connection_id: UUID) -> None:
        await self._sessions_service.validate_publisher(connection_id)
