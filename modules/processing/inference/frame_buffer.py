from collections import OrderedDict
from uuid import UUID

from modules.processing.schemas import QueuedFrame


class FrameBuffer:
    """Keep the latest pending frame and one in-flight claim per connection."""

    def __init__(self) -> None:
        self._pending: OrderedDict[UUID, QueuedFrame] = OrderedDict()
        self._in_flight: set[UUID] = set()

    def put_latest(self, work: QueuedFrame) -> bool:
        was_replaced = work.connection_id in self._pending
        self._pending[work.connection_id] = work
        return was_replaced

    def claim_batch(self, size: int) -> tuple[QueuedFrame, ...]:
        """Claim up to a positive size supplied by the scheduler."""
        batch: list[QueuedFrame] = []
        for connection_id in tuple(self._pending):
            if connection_id in self._in_flight:
                continue
            work = self._pending.pop(connection_id)
            self._in_flight.add(connection_id)
            batch.append(work)
            if len(batch) == size:
                break
        return tuple(batch)

    def release_batch(self, batch: tuple[QueuedFrame, ...]) -> None:
        self._in_flight.difference_update(work.connection_id for work in batch)

    def discard_pending(self, connection_id: UUID) -> None:
        self._pending.pop(connection_id, None)

    def pending_count(self, connection_id: UUID) -> int:
        return int(connection_id in self._pending)

    def is_in_flight(self, connection_id: UUID) -> bool:
        return connection_id in self._in_flight
