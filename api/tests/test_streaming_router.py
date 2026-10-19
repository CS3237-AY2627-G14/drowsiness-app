import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
import socketio
from anyio import CancelScope

from core.config import Settings
from modules.processing.schemas import FrameMeasurements, QueuedFrame
from modules.sessions.exceptions import SessionAccessException
from modules.streaming.facade import StreamingFacade
from modules.streaming.router import StreamingSocketRouter
from modules.streaming.utils.parse_frame import FRAME_HEADER
from tests.helpers import MutableClock, MutableTimer, build_streaming_runtime

AUTH = {"seat_id": 1, "token": "demo-room-101-seat-1"}
ENVIRON = {"HTTP_ORIGIN": "http://localhost:3000"}


@pytest.mark.parametrize("cause", ["idle", "expiry", "worker", "frame_error"])
def test_monitor_closes_connection_without_status_reporting(
    clock: MutableClock, monkeypatch: pytest.MonkeyPatch, cause: str
) -> None:
    async def run() -> None:
        timer = MutableTimer()
        worker_finished = asyncio.Event()
        disconnected = asyncio.Event()

        class FailingFramePredictor:
            async def predict_batch(
                self,
                batch: tuple[QueuedFrame, ...],
            ) -> tuple[FrameMeasurements, ...]:
                worker_finished.set()
                if cause == "worker":
                    raise RuntimeError("Worker failed")
                work = batch[0]
                return (
                    FrameMeasurements(
                        connection_id=work.connection_id,
                        frame_id=work.frame.frame_id,
                        captured_at_ms=work.frame.captured_at_ms,
                        error="invalid_frame",
                    ),
                )

        frame_predictor = FailingFramePredictor()

        runtime = build_streaming_runtime(
            clock, timer=timer, frame_predictor=frame_predictor
        )
        server = socketio.AsyncServer(async_mode="asgi")
        router = StreamingSocketRouter(
            server, StreamingFacade(runtime.streaming_service), Settings()
        )
        emit = AsyncMock()
        monkeypatch.setattr(server, "emit", emit)

        async def disconnect(sid: str) -> None:
            await router.disconnect(sid)
            disconnected.set()

        monkeypatch.setattr(server, "disconnect", disconnect)
        await router.connect("camera", ENVIRON, AUTH)
        connection_id = router._connections["camera"].connection_id
        monitor, reporter = router._tasks["camera"]
        reporter.cancel()
        await asyncio.gather(reporter, return_exceptions=True)
        runtime.frame_processing_service.start(1)
        try:
            if cause == "idle":
                timer.current_time = 10.0
                expected_code = "stream_idle"
            elif cause == "expiry":
                clock.current_time += timedelta(hours=2)
                expected_code = "session_expired"
            else:
                payload = FRAME_HEADER.pack(1, 1.0) + b"jpeg"
                await router.receive_frame("camera", payload)
                await asyncio.wait_for(worker_finished.wait(), 1)
                expected_code = (
                    "server_unavailable" if cause == "worker" else "invalid_frame"
                )
            await asyncio.wait_for(disconnected.wait(), 2)
            await asyncio.wait_for(monitor, 1)
            emit.assert_awaited_once_with(
                "stream_error", {"type": "error", "code": expected_code}, to="camera"
            )
            assert not router._connections
            assert not router._tasks
            assert not router._cleanups
            assert runtime.streaming_registry.get(connection_id) is None
            assert runtime.processing_registry.get(connection_id) is None
            with pytest.raises(SessionAccessException, match="stream_closed"):
                await runtime.sessions_facade.validate_publisher(connection_id)
        finally:
            await router.stop()
            await runtime.frame_processing_service.stop()

    asyncio.run(run())


def test_overlapping_terminal_paths_cleanup_once(
    clock: MutableClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def run() -> None:
        runtime = build_streaming_runtime(clock)
        server = socketio.AsyncServer(async_mode="asgi")
        router = StreamingSocketRouter(
            server, StreamingFacade(runtime.streaming_service), Settings()
        )
        emitting = asyncio.Event()
        finish_emit = asyncio.Event()

        async def emit(event: str, data: object, *, to: str) -> None:
            emitting.set()
            await finish_emit.wait()

        monkeypatch.setattr(server, "emit", AsyncMock(side_effect=emit))
        monkeypatch.setattr(
            server, "disconnect", AsyncMock(side_effect=router.disconnect)
        )
        close = AsyncMock(wraps=runtime.streaming_service.close_stream)
        monkeypatch.setattr(runtime.streaming_service, "close_stream", close)
        await router.connect("camera", ENVIRON, AUTH)
        connection_id = router._connections["camera"].connection_id
        error = asyncio.create_task(
            router._disconnect_with_error("camera", "invalid_frame")
        )
        await asyncio.wait_for(emitting.wait(), 1)
        await router._disconnect_with_error("camera", "server_unavailable")
        await asyncio.wait_for(router.disconnect("camera"), 1)
        finish_emit.set()
        await asyncio.wait_for(error, 1)
        await router.disconnect("camera")
        close.assert_awaited_once_with(connection_id)
        assert not router._connections
        assert not router._tasks
        assert not router._cleanups
        assert not router._closing
        replacement = await runtime.streaming_service.open_stream(
            token="demo-room-101-seat-1", seat_id=1
        )
        await runtime.streaming_service.close_stream(replacement.connection_id)
        await router.stop()

    asyncio.run(run())


@pytest.mark.parametrize("cancellation", ["asyncio", "anyio"])
def test_cancelled_disconnect_finishes_cleanup(
    clock: MutableClock, monkeypatch: pytest.MonkeyPatch, cancellation: str
) -> None:
    async def run() -> None:
        runtime = build_streaming_runtime(clock)
        server = socketio.AsyncServer(async_mode="asgi")
        router = StreamingSocketRouter(
            server, StreamingFacade(runtime.streaming_service), Settings()
        )
        started = asyncio.Event()
        finish = asyncio.Event()
        close_connection = runtime.frame_processing_service.close_connection

        async def block_close(connection_id: UUID) -> None:
            started.set()
            await finish.wait()
            await close_connection(connection_id)

        monkeypatch.setattr(
            runtime.frame_processing_service, "close_connection", block_close
        )
        await router.connect("camera", ENVIRON, AUTH)
        connection_id = router._connections["camera"].connection_id
        scope = CancelScope()

        async def disconnect() -> None:
            with scope:
                await router.disconnect("camera")

        disconnecting = asyncio.create_task(disconnect())
        await asyncio.wait_for(started.wait(), 1)
        if cancellation == "asyncio":
            disconnecting.cancel()
        else:
            scope.cancel()
        finish.set()
        if cancellation == "asyncio":
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(disconnecting, 1)
        else:
            await asyncio.wait_for(disconnecting, 1)
        assert not router._connections
        assert not router._tasks
        assert not router._cleanups
        assert runtime.processing_registry.get(connection_id) is None
        replacement = await runtime.sessions_facade.open_publisher(
            token="demo-room-101-seat-1", seat_id=1
        )
        await runtime.sessions_facade.close_publisher(replacement.connection_id)
        await router.stop()

    asyncio.run(run())


def test_shutdown_waits_for_pending_disconnect(
    clock: MutableClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def run() -> None:
        runtime = build_streaming_runtime(clock)
        server = socketio.AsyncServer(async_mode="asgi")
        router = StreamingSocketRouter(
            server, StreamingFacade(runtime.streaming_service), Settings()
        )
        started = asyncio.Event()
        finish = asyncio.Event()
        close_connection = runtime.frame_processing_service.close_connection

        async def block_close(connection_id: UUID) -> None:
            started.set()
            await finish.wait()
            await close_connection(connection_id)

        monkeypatch.setattr(
            runtime.frame_processing_service, "close_connection", block_close
        )
        shutdown = AsyncMock()
        monkeypatch.setattr(server, "shutdown", shutdown)
        await router.connect("camera", ENVIRON, AUTH)
        disconnecting = asyncio.create_task(router.disconnect("camera"))
        await asyncio.wait_for(started.wait(), 1)
        stopping = asyncio.create_task(router.stop())
        await asyncio.sleep(0)
        assert not stopping.done()
        shutdown.assert_not_awaited()
        finish.set()
        await asyncio.wait_for(asyncio.gather(disconnecting, stopping), 1)
        shutdown.assert_awaited_once()
        assert not router._cleanups
        assert not router._tasks
        replacement = await runtime.sessions_facade.open_publisher(
            token="demo-room-101-seat-1", seat_id=1
        )
        await runtime.sessions_facade.close_publisher(replacement.connection_id)

    asyncio.run(run())
