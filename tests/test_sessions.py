import asyncio
from datetime import timedelta
from uuid import uuid4

import pytest

from modules.classrooms.facade import SeatInfo
from modules.sessions.exceptions import SessionAccessException
from modules.sessions.facade import PublisherSession
from modules.sessions.repositories.publisher_repository import (
    InMemoryPublisherRepository,
)
from modules.sessions.repositories.stream_session_repository import (
    InMemoryStreamSessionRepository,
)
from modules.sessions.schemas import StreamSessionRecord
from modules.sessions.utils import hash_token
from tests.helpers import MutableClock, build_sessions


@pytest.mark.parametrize(
    "state", ["revoked", "ended", "expired", "unknown_seat", "wrong_seat"]
)
def test_session_state_is_enforced(clock: MutableClock, state: str) -> None:
    session = StreamSessionRecord(
        id=uuid4(),
        seat_id=99 if state == "unknown_seat" else 1,
        token_hash=hash_token("test-token"),
        created_at=clock.now() - timedelta(hours=2),
        expires_at=clock.now()
        if state == "expired"
        else clock.now() + timedelta(hours=1),
        revoked_at=clock.now() if state == "revoked" else None,
        ended_at=clock.now() if state == "ended" else None,
    )
    sessions_facade = build_sessions(clock, sessions=[session])
    with pytest.raises(SessionAccessException, match="unauthorized"):
        asyncio.run(
            sessions_facade.open_publisher(
                token="test-token",
                seat_id=2 if state == "wrong_seat" else session.seat_id,
            )
        )


def test_authorization_uses_seat_id_not_physical_number(clock: MutableClock) -> None:
    seat = SeatInfo(id=42, room_id=101, seat_number=7)
    session = StreamSessionRecord(
        id=uuid4(),
        seat_id=42,
        token_hash=hash_token("test-token"),
        created_at=clock.now(),
        expires_at=clock.now() + timedelta(hours=1),
    )
    sessions_facade = build_sessions(clock, sessions=[session], seats=[seat])
    with pytest.raises(SessionAccessException):
        asyncio.run(sessions_facade.open_publisher(token="test-token", seat_id=7))
    assert (
        asyncio.run(
            sessions_facade.open_publisher(token="test-token", seat_id=42)
        ).seat_id
        == 42
    )


def test_old_connection_cannot_release_new_publisher(clock: MutableClock) -> None:
    sessions_facade = build_sessions(clock)

    async def run() -> None:
        first = await sessions_facade.open_publisher(
            token="demo-room-101-seat-1", seat_id=1
        )
        with pytest.raises(SessionAccessException, match="seat_busy"):
            await sessions_facade.open_publisher(
                token="demo-room-101-seat-1", seat_id=1
            )
        await sessions_facade.close_publisher(first.connection_id)
        second = await sessions_facade.open_publisher(
            token="demo-room-101-seat-1", seat_id=1
        )
        await sessions_facade.close_publisher(first.connection_id)
        with pytest.raises(SessionAccessException, match="seat_busy"):
            await sessions_facade.open_publisher(
                token="demo-room-101-seat-1", seat_id=1
            )
        await sessions_facade.close_publisher(second.connection_id)

    asyncio.run(run())


def test_memory_rejects_multiple_open_sessions(clock: MutableClock) -> None:
    session = StreamSessionRecord(
        id=uuid4(),
        seat_id=1,
        token_hash=hash_token("first"),
        created_at=clock.now(),
        expires_at=clock.now() + timedelta(hours=1),
    )
    another = session.model_copy(
        update={"id": uuid4(), "token_hash": hash_token("second")}
    )
    with pytest.raises(ValueError, match="multiple open sessions"):
        InMemoryStreamSessionRepository([session, another])


def test_history_retained_but_ended_session_denied(clock: MutableClock) -> None:
    old = StreamSessionRecord(
        id=uuid4(),
        seat_id=1,
        token_hash=hash_token("old"),
        created_at=clock.now() - timedelta(hours=1),
        expires_at=clock.now() + timedelta(hours=1),
        ended_at=clock.now(),
    )
    current = old.model_copy(
        update={"id": uuid4(), "token_hash": hash_token("new"), "ended_at": None}
    )
    stream_session_repository = InMemoryStreamSessionRepository([old, current])
    assert (
        asyncio.run(stream_session_repository.get_by_token_hash(old.token_hash)) == old
    )
    sessions_facade = build_sessions(clock, sessions=[old, current])
    with pytest.raises(SessionAccessException):
        asyncio.run(sessions_facade.open_publisher(token="old", seat_id=1))
    assert (
        asyncio.run(sessions_facade.open_publisher(token="new", seat_id=1)).session_id
        == current.id
    )


def test_publisher_capacity_is_released_with_ownership(clock: MutableClock) -> None:
    publisher_repository = InMemoryPublisherRepository()
    first, second = (
        PublisherSession(
            connection_id=uuid4(),
            session_id=uuid4(),
            seat_id=seat,
            expires_at=clock.now() + timedelta(hours=1),
        )
        for seat in (1, 2)
    )

    async def run() -> None:
        assert await publisher_repository.claim_publisher(first, limit=1) is None
        assert (
            await publisher_repository.claim_publisher(second, limit=1)
            == "capacity_reached"
        )
        await publisher_repository.release_publisher(first.connection_id)
        assert await publisher_repository.claim_publisher(second, limit=1) is None

    asyncio.run(run())


def test_active_publisher_expiry_and_release(clock: MutableClock) -> None:
    async def run() -> None:
        sessions_facade = build_sessions(clock)
        publisher = await sessions_facade.open_publisher(
            token="demo-room-101-seat-1", seat_id=1
        )
        await sessions_facade.validate_publisher(publisher.connection_id)
        clock.current_time = publisher.expires_at
        with pytest.raises(SessionAccessException, match="session_expired"):
            await sessions_facade.validate_publisher(publisher.connection_id)
        await sessions_facade.close_publisher(publisher.connection_id)
        with pytest.raises(SessionAccessException, match="stream_closed"):
            await sessions_facade.validate_publisher(publisher.connection_id)

    asyncio.run(run())
