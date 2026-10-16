import asyncio
from uuid import UUID

from core.clock import MonotonicTimer, Timer
from modules.processing.facade import FrameInput, ProcessingException, ProcessingFacade
from modules.sessions.facade import (
    PublisherSession,
    SessionAccessException,
    SessionsFacade,
)
from modules.streaming.repositories.registry import StreamingRegistry
from modules.streaming.schemas import (
    StreamDiagnostics,
    StreamError,
    StreamingRecord,
    StreamStatus,
)
from modules.streaming.utils.wait_for_cleanup import wait_for_cleanup


class StreamingService:
    """Coordinate publishing connections and their frame processing."""

    def __init__(
        self,
        streaming_registry: StreamingRegistry,
        sessions_facade: SessionsFacade,
        processing_facade: ProcessingFacade,
        timer: Timer | None = None,
    ) -> None:
        self._streaming_registry = streaming_registry
        self._sessions_facade = sessions_facade
        self._processing_facade = processing_facade
        self._timer = timer if timer is not None else MonotonicTimer()
        self._closing: dict[UUID, asyncio.Task[None]] = {}

    async def open_stream(self, *, token: str, seat_id: int) -> PublisherSession:
        try:
            publisher = await self._sessions_facade.open_publisher(
                token=token, seat_id=seat_id
            )
        except SessionAccessException as error:
            raise StreamError(error.code) from error
        try:
            await self._processing_facade.open_connection(publisher.connection_id)
            opened_at = self._timer.now()
            record = StreamingRecord(
                publisher=publisher, last_received_at=opened_at, sample_at=opened_at
            )
            self._streaming_registry.save(publisher.connection_id, record)
        except BaseException as error:
            self._streaming_registry.remove(publisher.connection_id)
            cleanup = asyncio.create_task(
                self._release_connection(publisher.connection_id)
            )
            await wait_for_cleanup(cleanup)
            if isinstance(error, ProcessingException):
                raise StreamError(error.code) from error
            raise
        return publisher

    def _get_record(self, connection_id: UUID) -> StreamingRecord:
        record = self._streaming_registry.get(connection_id)
        if record is None:
            raise StreamError("stream_closed")
        return record

    async def _validate_publisher(self, connection_id: UUID) -> None:
        try:
            await self._sessions_facade.validate_publisher(connection_id)
        except SessionAccessException as error:
            raise StreamError(error.code) from error

    async def submit_frame(self, connection_id: UUID, frame: FrameInput) -> None:
        record = self._get_record(connection_id)
        await self._validate_publisher(connection_id)
        if (
            frame.frame_id <= record.last_frame_id
            or frame.captured_at_ms <= record.last_capture_ms
        ):
            raise StreamError("invalid_frame")
        received_at = self._timer.now()
        try:
            await self._processing_facade.submit_frame(connection_id, frame)
        except ProcessingException as error:
            raise StreamError(error.code) from error
        updated_record = record.model_copy(
            update={
                "last_frame_id": frame.frame_id,
                "last_capture_ms": frame.captured_at_ms,
                "last_received_at": received_at,
                "received_frames": record.received_frames + 1,
                "received_bytes": record.received_bytes + len(frame.jpeg),
            }
        )
        self._streaming_registry.save(connection_id, updated_record)

    async def check_stream(self, connection_id: UUID) -> None:
        record = self._get_record(connection_id)
        await self._validate_publisher(connection_id)
        if self._timer.now() - record.last_received_at >= 10:
            raise StreamError("stream_idle")
        try:
            await self._processing_facade.get_status(connection_id)
        except ProcessingException as error:
            raise StreamError(error.code) from error

    async def get_status(self, connection_id: UUID) -> StreamStatus:
        record = self._get_record(connection_id)
        try:
            processing_status = await self._processing_facade.get_status(connection_id)
        except ProcessingException as error:
            raise StreamError(error.code) from error
        now = self._timer.now()
        elapsed = max(now - record.sample_at, 0.001)
        diagnostics = StreamDiagnostics(
            received_frames=record.received_frames,
            processed_frames=processing_status.processed_frames,
            replaced_frames=processing_status.replaced_frames,
            stale_frames=processing_status.stale_frames,
            received_fps=(record.received_frames - record.sample_received_frames)
            / elapsed,
            processed_fps=(
                processing_status.processed_frames - record.sample_processed_frames
            )
            / elapsed,
            upload_kbps=(record.received_bytes - record.sample_received_bytes)
            * 8
            / elapsed
            / 1000,
            last_received_frame_id=record.last_frame_id,
            pending_frames=processing_status.pending_frames,
            in_flight=processing_status.in_flight,
        )
        sampled_record = record.model_copy(
            update={
                "sample_at": now,
                "sample_received_frames": record.received_frames,
                "sample_processed_frames": processing_status.processed_frames,
                "sample_received_bytes": record.received_bytes,
            }
        )
        self._streaming_registry.save(connection_id, sampled_record)
        return StreamStatus(
            diagnostics=diagnostics, detection=processing_status.detection
        )

    async def close_stream(self, connection_id: UUID) -> None:
        cleanup = self._closing.get(connection_id)
        if cleanup is None:
            record = self._streaming_registry.remove(connection_id)
            if record is None:
                return
            cleanup = asyncio.create_task(self._release_connection(connection_id))
            self._closing[connection_id] = cleanup
        try:
            await wait_for_cleanup(cleanup)
        finally:
            if cleanup.done():
                self._closing.pop(connection_id, None)

    async def _release_connection(self, connection_id: UUID) -> None:
        try:
            await self._processing_facade.close_connection(connection_id)
        finally:
            await self._sessions_facade.close_publisher(connection_id)
