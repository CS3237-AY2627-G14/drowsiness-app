from typing import Protocol

from modules.sessions.schemas import StreamSessionRecord


class StreamSessionRepository(Protocol):
    async def get_by_token_hash(
        self, token_hash: str
    ) -> StreamSessionRecord | None: ...


class InMemoryStreamSessionRepository:
    def __init__(self, sessions: list[StreamSessionRecord]) -> None:
        self._sessions: dict[str, StreamSessionRecord] = {}
        open_seats: set[int] = set()
        for session in sessions:
            if session.token_hash in self._sessions:
                raise ValueError("Session token hashes must be unique")
            if session.ended_at is None:
                if session.seat_id in open_seats:
                    raise ValueError("A seat cannot have multiple open sessions")
                open_seats.add(session.seat_id)
            self._sessions[session.token_hash] = session

    async def get_by_token_hash(self, token_hash: str) -> StreamSessionRecord | None:
        return self._sessions.get(token_hash)
