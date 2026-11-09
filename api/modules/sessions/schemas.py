from typing import Annotated
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    StringConstraints,
)


class StreamSessionRecord(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)
    id: UUID
    seat_id: str
    token_hash: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
    created_at: AwareDatetime
    expires_at: AwareDatetime
    revoked_at: AwareDatetime | None = None
    ended_at: AwareDatetime | None = None


class PublisherSession(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)
    connection_id: UUID
    session_id: UUID
    seat_id: str
    expires_at: AwareDatetime
