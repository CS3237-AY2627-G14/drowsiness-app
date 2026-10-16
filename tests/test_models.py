from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import Connection, create_engine, create_mock_engine, insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import configure_mappers
from sqlalchemy.schema import CreateIndex, CreateTable

from core.database import Base
from modules.classrooms.models import RoomModel, SeatModel
from modules.sessions.models import StreamSessionModel
from modules.sessions.utils import hash_token


@pytest.fixture
def connection() -> Iterator[Connection]:
    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as database:
        database.exec_driver_sql("PRAGMA foreign_keys=ON")
        Base.metadata.create_all(database)
        room_insert = insert(RoomModel).values(id=101, name="Room 101")
        database.execute(room_insert)
        seat_insert = insert(SeatModel).values(id=1, room_id=101, seat_number=1)
        database.execute(seat_insert)
        database.commit()
        yield database
    engine.dispose()


def add_session(
    connection: Connection,
    *,
    token: str,
    seat_id: int = 1,
    ended: bool = False,
    expired: bool = False,
) -> None:
    now = datetime(2026, 10, 14, tzinfo=UTC)
    session_id = uuid4()
    token_hash = hash_token(token)
    expires_at = now - timedelta(seconds=1) if expired else now + timedelta(hours=1)
    session_insert = insert(StreamSessionModel).values(
        id=session_id,
        seat_id=seat_id,
        token_hash=token_hash,
        created_at=now,
        expires_at=expires_at,
        ended_at=now if ended else None,
    )
    connection.execute(session_insert)


def test_mappings_and_postgresql_schema_compile() -> None:
    configure_mappers()
    engine = create_mock_engine("postgresql://", lambda *args, **kwargs: None)
    dialect = engine.dialect
    for table in Base.metadata.sorted_tables:
        assert str(CreateTable(table).compile(dialect=dialect))
        for index in table.indexes:
            assert str(CreateIndex(index).compile(dialect=dialect))
    room = RoomModel(id=101, name="Room 101")
    seat = SeatModel(id=1, seat_number=1, room=room)
    assert room.seats == [seat]


@pytest.mark.parametrize("seat_number", [0, -1, 1])
def test_invalid_or_duplicate_seat_is_rejected(
    connection: Connection, seat_number: int
) -> None:
    with pytest.raises(IntegrityError):
        seat_insert = insert(SeatModel).values(
            id=2, room_id=101, seat_number=seat_number
        )
        connection.execute(seat_insert)


def test_same_seat_number_can_exist_in_another_room(connection: Connection) -> None:
    room_insert = insert(RoomModel).values(id=102, name="Room 102")
    connection.execute(room_insert)
    seat_insert = insert(SeatModel).values(id=2, room_id=102, seat_number=1)
    connection.execute(seat_insert)


def test_session_requires_existing_seat(connection: Connection) -> None:
    with pytest.raises(IntegrityError):
        add_session(connection, token="missing-seat", seat_id=999)


def test_only_one_open_session_is_allowed(connection: Connection) -> None:
    add_session(connection, token="first")
    with pytest.raises(IntegrityError):
        add_session(connection, token="second")


def test_ended_sessions_allow_new_session(connection: Connection) -> None:
    add_session(connection, token="first", ended=True)
    add_session(connection, token="second", ended=True)
    add_session(connection, token="current")


def test_token_hash_is_unique_even_in_history(connection: Connection) -> None:
    add_session(connection, token="same", ended=True)
    with pytest.raises(IntegrityError):
        add_session(connection, token="same")


def test_expiry_must_follow_creation(connection: Connection) -> None:
    with pytest.raises(IntegrityError):
        add_session(connection, token="invalid-expiry", expired=True)
