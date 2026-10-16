import asyncio
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from modules.processing.exceptions import ProcessingException
from modules.processing.facade import FrameInput
from modules.processing.schemas import FrameMeasurements, QueuedFrame
from modules.sessions.exceptions import SessionAccessException
from modules.streaming.exceptions import StreamException
from tests.helpers import (
    FakeFramePredictor,
    MutableClock,
    MutableTimer,
    build_streaming_runtime,
)


@pytest.mark.parametrize(("frame_id", "captured_at_ms"), [(1, 200.0), (2, 100.0)])
def test_frame_admission_and_upload_metrics(
    clock: MutableClock, frame_id: int, captured_at_ms: float
) -> None:
    async def run() -> None:
        timer = MutableTimer()
        runtime = build_streaming_runtime(clock, timer=timer)
        publisher = await runtime.streaming_service.open_stream(
            token="demo-room-101-seat-1", seat_id=1
        )
        first = FrameInput(frame_id=1, captured_at_ms=100.0, jpeg=b"jpeg")
        await runtime.streaming_service.submit_frame(publisher.connection_id, first)
        invalid = FrameInput(
            frame_id=frame_id, captured_at_ms=captured_at_ms, jpeg=b"jpeg"
        )
        with pytest.raises(StreamException, match="invalid_frame"):
            await runtime.streaming_service.submit_frame(
                publisher.connection_id, invalid
            )
        second = FrameInput(frame_id=2, captured_at_ms=200.0, jpeg=b"jpeg")
        await runtime.streaming_service.submit_frame(publisher.connection_id, second)
        timer.current_time = 2.0
        status = await runtime.streaming_service.get_status(publisher.connection_id)
        assert status.diagnostics.received_frames == 2
        assert status.diagnostics.received_fps == 1.0
        assert status.diagnostics.upload_kbps == 0.032
        assert status.diagnostics.last_received_frame_id == 2
        assert status.diagnostics.replaced_frames == 1
        assert status.diagnostics.pending_frames == 1
        timer.current_time = 3.0
        next_status = await runtime.streaming_service.get_status(
            publisher.connection_id
        )
        assert next_status.diagnostics.received_fps == 0
        assert next_status.diagnostics.upload_kbps == 0
        await runtime.streaming_service.close_stream(publisher.connection_id)

    asyncio.run(run())


def test_failed_admission_does_not_increment_upload_counters(
    clock: MutableClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def run() -> None:
        runtime = build_streaming_runtime(clock)
        publisher = await runtime.streaming_service.open_stream(
            token="demo-room-101-seat-1", seat_id=1
        )
        monkeypatch.setattr(
            runtime.frame_processing_service,
            "submit_frame",
            AsyncMock(side_effect=ProcessingException("server_unavailable")),
        )
        frame = FrameInput(frame_id=1, captured_at_ms=1.0, jpeg=b"jpeg")
        with pytest.raises(StreamException, match="server_unavailable"):
            await runtime.streaming_service.submit_frame(publisher.connection_id, frame)
        status = await runtime.streaming_service.get_status(publisher.connection_id)
        assert status.diagnostics.received_frames == 0
        assert status.diagnostics.last_received_frame_id == 0
        assert status.diagnostics.pending_frames == 0
        await runtime.streaming_service.close_stream(publisher.connection_id)

    asyncio.run(run())


@pytest.mark.parametrize(
    "failure",
    [ProcessingException("server_unavailable"), RuntimeError("Initialization failed")],
)
def test_initialization_failure_removes_partial_state_and_releases_seat(
    clock: MutableClock, monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    async def run() -> None:
        runtime = build_streaming_runtime(clock)
        opened: list[UUID] = []
        open_connection = runtime.frame_processing_service.open_connection

        async def fail_open(connection_id: UUID) -> None:
            opened.append(connection_id)
            await open_connection(connection_id)
            raise failure

        monkeypatch.setattr(
            runtime.frame_processing_service, "open_connection", fail_open
        )
        expected = (
            StreamException
            if isinstance(failure, ProcessingException)
            else RuntimeError
        )
        with pytest.raises(expected):
            await runtime.streaming_service.open_stream(
                token="demo-room-101-seat-1", seat_id=1
            )
        assert runtime.processing_registry.get(opened[0]) is None
        assert runtime.streaming_registry.get(opened[0]) is None
        replacement = await runtime.sessions_facade.open_publisher(
            token="demo-room-101-seat-1", seat_id=1
        )
        await runtime.sessions_facade.close_publisher(replacement.connection_id)

    asyncio.run(run())


def test_cancelled_initialization_releases_seat(
    clock: MutableClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def run() -> None:
        runtime = build_streaming_runtime(clock)
        started = asyncio.Event()
        finish = asyncio.Event()
        opened: list[UUID] = []
        open_connection = runtime.frame_processing_service.open_connection

        async def block_open(connection_id: UUID) -> None:
            opened.append(connection_id)
            await open_connection(connection_id)
            started.set()
            await finish.wait()

        monkeypatch.setattr(
            runtime.frame_processing_service, "open_connection", block_open
        )
        opening = asyncio.create_task(
            runtime.streaming_service.open_stream(
                token="demo-room-101-seat-1", seat_id=1
            )
        )
        await asyncio.wait_for(started.wait(), 1)
        opening.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(opening, 1)
        assert runtime.processing_registry.get(opened[0]) is None
        assert runtime.streaming_registry.get(opened[0]) is None
        replacement = await runtime.sessions_facade.open_publisher(
            token="demo-room-101-seat-1", seat_id=1
        )
        await runtime.sessions_facade.close_publisher(replacement.connection_id)

    asyncio.run(run())


def test_concurrent_close_finishes_once_despite_caller_cancellation(
    clock: MutableClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def run() -> None:
        runtime = build_streaming_runtime(clock)
        publisher = await runtime.streaming_service.open_stream(
            token="demo-room-101-seat-1", seat_id=1
        )
        started = asyncio.Event()
        finish = asyncio.Event()
        close_publisher = runtime.sessions_facade.close_publisher

        async def block_release(connection_id: UUID) -> None:
            started.set()
            await finish.wait()
            await close_publisher(connection_id)

        release = AsyncMock(side_effect=block_release)
        close_processing = AsyncMock(
            wraps=runtime.frame_processing_service.close_connection
        )
        monkeypatch.setattr(runtime.sessions_facade, "close_publisher", release)
        monkeypatch.setattr(
            runtime.frame_processing_service, "close_connection", close_processing
        )
        first = asyncio.create_task(
            runtime.streaming_service.close_stream(publisher.connection_id)
        )
        await asyncio.wait_for(started.wait(), 1)
        second = asyncio.create_task(
            runtime.streaming_service.close_stream(publisher.connection_id)
        )
        first.cancel("disconnect requested")
        await asyncio.sleep(0)
        first.cancel("disconnect requested again")
        finish.set()
        with pytest.raises(asyncio.CancelledError, match="disconnect requested again"):
            await asyncio.wait_for(first, 1)
        await asyncio.wait_for(second, 1)
        await runtime.streaming_service.close_stream(publisher.connection_id)
        release.assert_awaited_once_with(publisher.connection_id)
        close_processing.assert_awaited_once_with(publisher.connection_id)
        assert runtime.streaming_registry.get(publisher.connection_id) is None
        assert runtime.processing_registry.get(publisher.connection_id) is None
        replacement = await runtime.sessions_facade.open_publisher(
            token="demo-room-101-seat-1", seat_id=1
        )
        await runtime.sessions_facade.close_publisher(replacement.connection_id)

    asyncio.run(run())


def test_processing_cleanup_failure_still_releases_seat(
    clock: MutableClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def run() -> None:
        runtime = build_streaming_runtime(clock)
        publisher = await runtime.streaming_service.open_stream(
            token="demo-room-101-seat-1", seat_id=1
        )
        close_connection = runtime.frame_processing_service.close_connection

        async def fail_close(connection_id: UUID) -> None:
            await close_connection(connection_id)
            raise RuntimeError("Cleanup failed")

        monkeypatch.setattr(
            runtime.frame_processing_service, "close_connection", fail_close
        )
        with pytest.raises(RuntimeError, match="Cleanup failed"):
            await runtime.streaming_service.close_stream(publisher.connection_id)
        replacement = await runtime.sessions_facade.open_publisher(
            token="demo-room-101-seat-1", seat_id=1
        )
        await runtime.sessions_facade.close_publisher(replacement.connection_id)

    asyncio.run(run())


def test_reconnect_does_not_receive_old_inflight_detection(clock: MutableClock) -> None:
    async def run() -> None:
        started = asyncio.Event()
        finish = asyncio.Event()
        returned = asyncio.Event()
        fake_frame_predictor = FakeFramePredictor()

        class BlockingFramePredictor:
            async def predict_batch(
                self,
                batch: tuple[QueuedFrame, ...],
            ) -> tuple[FrameMeasurements, ...]:
                started.set()
                await finish.wait()
                measurements = await fake_frame_predictor.predict_batch(batch)
                returned.set()
                return measurements

        frame_predictor = BlockingFramePredictor()

        runtime = build_streaming_runtime(clock, frame_predictor=frame_predictor)
        runtime.frame_processing_service.start(1)
        try:
            first = await runtime.streaming_service.open_stream(
                token="demo-room-101-seat-1", seat_id=1
            )
            frame = FrameInput(frame_id=1, captured_at_ms=1.0, jpeg=b"jpeg")
            await runtime.streaming_service.submit_frame(first.connection_id, frame)
            await asyncio.wait_for(started.wait(), 1)
            await runtime.streaming_service.close_stream(first.connection_id)
            assert runtime.frame_buffer.is_in_flight(first.connection_id)
            replacement = await runtime.streaming_service.open_stream(
                token="demo-room-101-seat-1", seat_id=1
            )
            assert replacement.session_id == first.session_id
            assert replacement.connection_id != first.connection_id
            finish.set()
            await asyncio.wait_for(returned.wait(), 1)
            status = await runtime.streaming_service.get_status(
                replacement.connection_id
            )
            assert status.detection is None
            assert status.diagnostics.processed_frames == 0
            assert not runtime.frame_buffer.is_in_flight(first.connection_id)
            assert runtime.processing_registry.get(first.connection_id) is None
            with pytest.raises(SessionAccessException, match="stream_closed"):
                await runtime.sessions_facade.validate_publisher(first.connection_id)
            await runtime.streaming_service.close_stream(replacement.connection_id)
        finally:
            await runtime.frame_processing_service.stop()

    asyncio.run(run())
