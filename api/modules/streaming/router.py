import asyncio
import logging
from typing import Any

import socketio
from anyio import CancelScope
from pydantic import ValidationError

from core.config import Settings
from modules.streaming.exceptions import StreamException
from modules.streaming.facade import StreamingFacade
from modules.streaming.schemas import AuthenticateMessage, SocketConnection
from modules.streaming.utils.build_stream_response import build_stream_response
from modules.streaming.utils.parse_frame import parse_frame
from modules.streaming.utils.wait_for_cleanup import wait_for_cleanup

logger = logging.getLogger(__name__)


class StreamingSocketRouter:
    def __init__(
        self,
        socket_server: socketio.AsyncServer,
        streaming_facade: StreamingFacade,
        settings: Settings,
    ) -> None:
        self._socket_server = socket_server
        self._streaming_facade = streaming_facade
        self._settings = settings
        self._connections: dict[str, SocketConnection] = {}
        self._tasks: dict[str, tuple[asyncio.Task[None], ...]] = {}
        self._closing: set[str] = set()
        self._cleanups: set[asyncio.Task[None]] = set()
        socket_server.on("connect", self.connect)
        socket_server.on("disconnect", self.disconnect)
        socket_server.on("frame", self.receive_frame)
        socket_server.on("*", self.unexpected_event)

    async def connect(
        self, sid: str, environ: dict[str, Any], auth: object = None
    ) -> None:
        if environ.get("HTTP_ORIGIN") not in self._settings.allowed_origins:
            raise socketio.exceptions.ConnectionRefusedError(
                "Publishing denied", {"code": "unauthorized"}
            )
        try:
            credentials = AuthenticateMessage.model_validate(auth)
        except ValidationError:
            raise socketio.exceptions.ConnectionRefusedError(
                "Publishing denied", {"code": "unauthorized"}
            ) from None
        token = credentials.token.get_secret_value()
        try:
            publisher = await self._streaming_facade.open_stream(
                token=token, seat_id=credentials.seat_id
            )
        except StreamException as error:
            raise socketio.exceptions.ConnectionRefusedError(
                "Publishing denied", {"code": error.code}
            ) from None
        self._connections[sid] = SocketConnection(
            connection_id=publisher.connection_id, diagnostics=credentials.diagnostics
        )
        logger.info(
            "Stream connected seat_id=%d connection_id=%s",
            credentials.seat_id,
            publisher.connection_id,
        )
        self._tasks[sid] = (
            asyncio.create_task(self._monitor_stream(sid)),
            asyncio.create_task(self._send_status(sid)),
        )

    async def receive_frame(self, sid: str, payload: object = None) -> None:
        connection = self._connections.get(sid)
        if connection is None or sid in self._closing:
            return
        try:
            frame = parse_frame(payload, self._settings.max_frame_bytes)
            await self._streaming_facade.submit_frame(connection.connection_id, frame)
        except StreamException as error:
            await self._disconnect_with_error(sid, error.code)

    async def unexpected_event(self, event: str, sid: str, *args: object) -> None:
        await self._disconnect_with_error(sid, "invalid_frame")

    async def disconnect(self, sid: str, reason: str | None = None) -> None:
        """Stop connection tasks and finish releasing the seat before returning."""
        connection = self._connections.pop(sid, None)
        if connection is None:
            return
        tasks = self._tasks.pop(sid, ())
        current = asyncio.current_task()
        # Monitoring or reporting may be the task requesting its own disconnect.
        other_tasks = tuple(task for task in tasks if task is not current)
        logger.info(
            "Stream disconnected connection_id=%s reason=%s",
            connection.connection_id,
            reason or "unknown",
        )
        # Cleanup must survive cancellation of the socket handler that requested it.
        cleanup = asyncio.create_task(self._finish_disconnect(connection, other_tasks))
        self._cleanups.add(cleanup)
        try:
            await wait_for_cleanup(cleanup)
        finally:
            self._cleanups.discard(cleanup)
            self._closing.discard(sid)

    async def _finish_disconnect(
        self, connection: SocketConnection, tasks: tuple[asyncio.Task[None], ...]
    ) -> None:
        for task in tasks:
            task.cancel()
        try:
            await self._streaming_facade.close_stream(connection.connection_id)
        finally:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def stop(self) -> None:
        for sid in tuple(self._connections):
            try:
                await self._socket_server.disconnect(sid)
            finally:
                await self.disconnect(sid)
        for cleanup in tuple(self._cleanups):
            await wait_for_cleanup(cleanup)
        await self._socket_server.shutdown()

    async def _emit_with_timeout(
        self, sid: str, event: str, data: dict[str, Any]
    ) -> None:
        async with asyncio.timeout(5):
            await self._socket_server.emit(event, data, to=sid)

    async def _disconnect_with_error(self, sid: str, code: str) -> None:
        connection = self._connections.get(sid)
        if connection is None or sid in self._closing:
            return
        self._closing.add(sid)
        logger.warning(
            "Stream error connection_id=%s code=%s", connection.connection_id, code
        )
        try:
            await self._emit_with_timeout(
                sid, "stream_error", {"type": "error", "code": code}
            )
        except TimeoutError:
            pass
        finally:
            with CancelScope(shield=True):
                try:
                    await self._socket_server.disconnect(sid)
                finally:
                    await self.disconnect(sid)

    async def _monitor_stream(self, sid: str) -> None:
        try:
            while sid in self._connections:
                await asyncio.sleep(1)
                connection = self._connections.get(sid)
                if connection is None:
                    return
                await self._streaming_facade.check_stream(connection.connection_id)
        except StreamException as error:
            await self._disconnect_with_error(sid, error.code)
        except Exception:
            logger.exception("Stream monitoring task failed")
            await self._disconnect_with_error(sid, "server_unavailable")

    async def _send_status(self, sid: str) -> None:
        try:
            while sid in self._connections:
                await asyncio.sleep(1)
                connection = self._connections.get(sid)
                if connection is None:
                    return
                status = await self._streaming_facade.get_status(
                    connection.connection_id
                )
                response = build_stream_response(status, connection.diagnostics)
                excluded_fields = (
                    {"diagnostics"} if response.diagnostics is None else None
                )
                payload = response.model_dump(mode="json", exclude=excluded_fields)
                await self._emit_with_timeout(sid, "status", payload)
        except StreamException as error:
            await self._disconnect_with_error(sid, error.code)
        except TimeoutError:
            await self._disconnect_with_error(sid, "connection_timeout")
        except Exception:
            logger.exception("Streaming status task failed")
            await self._disconnect_with_error(sid, "server_unavailable")
