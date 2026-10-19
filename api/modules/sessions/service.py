from uuid import UUID, uuid4

from core.clock import Clock
from modules.classrooms.facade import ClassroomsFacade
from modules.sessions.exceptions import SessionAccessException
from modules.sessions.repositories.publisher_repository import PublisherRepository
from modules.sessions.repositories.stream_session_repository import (
    StreamSessionRepository,
)
from modules.sessions.schemas import PublisherSession
from modules.sessions.utils import hash_token


class SessionsService:
    """Authorize publishers and manage exclusive ownership of seats."""

    def __init__(
        self,
        stream_session_repository: StreamSessionRepository,
        publisher_repository: PublisherRepository,
        classrooms_facade: ClassroomsFacade,
        clock: Clock,
        max_publishers: int,
    ) -> None:
        self._stream_session_repository = stream_session_repository
        self._publisher_repository = publisher_repository
        self._classrooms_facade = classrooms_facade
        self._clock = clock
        self._max_publishers = max_publishers

    async def open_publisher(self, *, token: str, seat_id: int) -> PublisherSession:
        token_hash = hash_token(token)
        session = await self._stream_session_repository.get_by_token_hash(token_hash)
        if (
            session is None
            or session.seat_id != seat_id
            or session.revoked_at is not None
            or session.ended_at is not None
        ):
            raise SessionAccessException("unauthorized")

        now = self._clock.now()
        if session.expires_at <= now:
            raise SessionAccessException("unauthorized")

        seat = await self._classrooms_facade.get_seat(seat_id)
        if seat is None:
            raise SessionAccessException("unauthorized")

        connection_id = uuid4()
        publisher = PublisherSession(
            connection_id=connection_id,
            session_id=session.id,
            seat_id=seat_id,
            expires_at=session.expires_at,
        )

        denial_reason = await self._publisher_repository.claim_publisher(
            publisher, self._max_publishers
        )
        if denial_reason:
            raise SessionAccessException(denial_reason)
        return publisher

    async def close_publisher(self, connection_id: UUID) -> None:
        await self._publisher_repository.release_publisher(connection_id)

    async def validate_publisher(self, connection_id: UUID) -> None:
        publisher = await self._publisher_repository.get_publisher(connection_id)
        if publisher is None:
            raise SessionAccessException("stream_closed")
        if publisher.expires_at <= self._clock.now():
            raise SessionAccessException("session_expired")
