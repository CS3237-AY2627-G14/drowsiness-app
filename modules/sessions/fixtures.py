from datetime import datetime, timedelta
from uuid import uuid4

from modules.classrooms.facade import SeatInfo
from modules.sessions.schemas import StreamSessionRecord
from modules.sessions.utils import hash_token


def create_demo_sessions(
    seats: list[SeatInfo], *, created_at: datetime, ttl_seconds: int
) -> list[StreamSessionRecord]:
    sessions: list[StreamSessionRecord] = []
    for seat in seats:
        session_id = uuid4()
        token = f"demo-room-{seat.room_id}-seat-{seat.seat_number}"
        token_hash = hash_token(token)
        expires_at = created_at + timedelta(seconds=ttl_seconds)
        session = StreamSessionRecord(
            id=session_id,
            seat_id=seat.id,
            token_hash=token_hash,
            created_at=created_at,
            expires_at=expires_at,
        )
        sessions.append(session)
    return sessions
