from typing import Protocol
from uuid import UUID

from modules.streaming.schemas import StreamingRecord


class StreamingRegistry(Protocol):
    """Synchronous connection state within one streaming runtime."""

    def get(self, connection_id: UUID) -> StreamingRecord | None: ...

    def save(self, connection_id: UUID, record: StreamingRecord) -> None: ...

    def remove(self, connection_id: UUID) -> StreamingRecord | None: ...


class InMemoryStreamingRegistry:
    def __init__(self) -> None:
        self._records: dict[UUID, StreamingRecord] = {}

    def get(self, connection_id: UUID) -> StreamingRecord | None:
        return self._records.get(connection_id)

    def save(self, connection_id: UUID, record: StreamingRecord) -> None:
        self._records[connection_id] = record

    def remove(self, connection_id: UUID) -> StreamingRecord | None:
        return self._records.pop(connection_id, None)
