from typing import Protocol
from uuid import UUID

from modules.processing.schemas import ProcessingRecord


class ProcessingRegistry(Protocol):
    def get(self, connection_id: UUID) -> ProcessingRecord | None: ...

    def save(self, connection_id: UUID, record: ProcessingRecord) -> None: ...

    def remove(self, connection_id: UUID) -> None: ...


class InMemoryProcessingRegistry:
    def __init__(self) -> None:
        self._records: dict[UUID, ProcessingRecord] = {}

    def get(self, connection_id: UUID) -> ProcessingRecord | None:
        return self._records.get(connection_id)

    def save(self, connection_id: UUID, record: ProcessingRecord) -> None:
        self._records[connection_id] = record

    def remove(self, connection_id: UUID) -> None:
        self._records.pop(connection_id, None)
