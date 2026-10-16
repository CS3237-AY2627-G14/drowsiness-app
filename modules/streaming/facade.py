from uuid import UUID

from modules.processing.facade import FrameInput
from modules.sessions.facade import PublisherSession
from modules.streaming.schemas import StreamError, StreamStatus
from modules.streaming.service import StreamingService

__all__ = [
    "FrameInput",
    "PublisherSession",
    "StreamError",
    "StreamingFacade",
    "StreamStatus",
]


class StreamingFacade:
    def __init__(self, streaming_service: StreamingService) -> None:
        self._streaming_service = streaming_service

    async def open_stream(self, *, token: str, seat_id: int) -> PublisherSession:
        return await self._streaming_service.open_stream(token=token, seat_id=seat_id)

    async def submit_frame(self, connection_id: UUID, frame: FrameInput) -> None:
        await self._streaming_service.submit_frame(connection_id, frame)

    async def get_status(self, connection_id: UUID) -> StreamStatus:
        return await self._streaming_service.get_status(connection_id)

    async def check_stream(self, connection_id: UUID) -> None:
        await self._streaming_service.check_stream(connection_id)

    async def close_stream(self, connection_id: UUID) -> None:
        await self._streaming_service.close_stream(connection_id)
