import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession
from starlette.websockets import WebSocketDisconnect

from modules.streaming.utils.parse_frame import FRAME_HEADER
from tests.helpers import MutableClock

HEADERS = {"origin": "http://localhost:3000", "upgrade": "websocket"}
ENDPOINT = "/api/socket.io/?EIO=4&transport=websocket"
AUTH = {"seat_id": 1, "token": "demo-room-101-seat-1"}


class SocketIOConnection:
    def __init__(self, socket: WebSocketTestSession) -> None:
        self.socket = socket
        self.closed = False
        assert socket.receive_text().startswith("0{")

    def authenticate(self, auth: object) -> None:
        authentication_json = json.dumps(auth)
        self.socket.send_text("40" + authentication_json)

    def receive(self) -> dict[str, Any]:
        while True:
            try:
                packet = self.socket.receive_text()
            except WebSocketDisconnect:
                self.closed = True
                raise
            if packet == "2":
                self.socket.send_text("3")
            elif packet.startswith("42"):
                event, data = json.loads(packet[2:])
                assert event in {"status", "stream_error"}
                assert isinstance(data, dict)
                return data
            elif packet.startswith("44"):
                error = json.loads(packet[2:])
                return {"type": "error", "code": error["data"]["code"]}
            else:
                assert packet.startswith("40")
                return {"type": "connected"}

    def send_frame(self, payload: bytes | str) -> None:
        if isinstance(payload, bytes):
            self.socket.send_text('451-["frame",{"_placeholder":true,"num":0}]')
            self.socket.send_bytes(payload)
        else:
            frame_event = json.dumps(["frame", payload])
            self.socket.send_text("42" + frame_event)


@contextmanager
def connect(client: TestClient) -> Iterator[SocketIOConnection]:
    with client.websocket_connect(ENDPOINT, headers=HEADERS) as socket:
        connection = SocketIOConnection(socket)
        try:
            yield connection
        finally:
            if not connection.closed:
                socket.send_text("41")
                socket.close()
                try:
                    while True:
                        socket.receive_text()
                except WebSocketDisconnect:
                    pass


def test_socketio_authentication_and_status(client: TestClient) -> None:
    with connect(client) as socket:
        socket.authenticate(AUTH)
        assert socket.receive()["type"] == "connected"
        frame_payload = FRAME_HEADER.pack(1, 100.0) + b"test"
        socket.send_frame(frame_payload)
        status = socket.receive()
        assert set(status) == {"type", "detection"}
        assert status["detection"]["minute"] == {
            "valid_samples": 1,
            "drowsy_samples": 0,
            "unavailable_samples": 59,
            "window_seconds": 60,
        }
        assert status["detection"]["alert"] is False
        assert "frame_id" not in status["detection"]
        assert "processing_ms" not in status["detection"]
        assert "fatigue_seconds" not in status["detection"]
        assert status["detection"]["fatigue_probability"] == 0.1
        assert status["detection"]["present"] is None


def test_diagnostics_are_explicitly_requested(client: TestClient) -> None:
    with connect(client) as socket:
        socket.authenticate({**AUTH, "diagnostics": True})
        assert socket.receive()["type"] == "connected"
        frame_payload = FRAME_HEADER.pack(1, 100.0) + b"test"
        socket.send_frame(frame_payload)
        status = socket.receive()
        assert set(status) == {"type", "detection", "diagnostics"}
        assert status["diagnostics"]["received_frames"] == 1
        assert status["diagnostics"]["processed_frames"] == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"seat_id": 1, "token": "invalid"},
        {"seat_id": 1, "token": "demo-room-101-seat-2"},
        {"seat_id": 1},
        {},
        {"seat_id": "1", "token": "demo-room-101-seat-1"},
        {"seat_id": 1, "token": "demo-room-101-seat-1", "extra": True},
        {"seat_id": 0, "token": "demo-room-101-seat-1"},
    ],
)
def test_denied_auth(client: TestClient, payload: dict[str, object]) -> None:
    with connect(client) as socket:
        socket.authenticate(payload)
        assert socket.receive() == {"type": "error", "code": "unauthorized"}


def test_origin_required(client: TestClient) -> None:
    with client.websocket_connect(ENDPOINT, headers={"upgrade": "websocket"}) as raw:
        socket = SocketIOConnection(raw)
        socket.authenticate(AUTH)
        assert socket.receive()["code"] == "unauthorized"


def test_unapproved_origin_rejected(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            ENDPOINT, headers={"origin": "https://unapproved.example"}
        ):
            pass


def test_polling_transport_disabled(client: TestClient) -> None:
    response = client.get("/api/socket.io/?EIO=4&transport=polling", headers=HEADERS)
    assert response.status_code == 400


def test_duplicate_publisher_and_release(client: TestClient) -> None:
    with connect(client) as first:
        first.authenticate(AUTH)
        first.receive()
        with connect(client) as second:
            second.authenticate(AUTH)
            assert second.receive()["code"] == "seat_busy"
    with connect(client) as retry:
        retry.authenticate(AUTH)
        assert retry.receive()["type"] == "connected"


def test_expiry_closes_connection(client: TestClient, clock: MutableClock) -> None:
    with connect(client) as socket:
        socket.authenticate(AUTH)
        socket.receive()
        clock.current_time += timedelta(hours=2)
        frame_payload = FRAME_HEADER.pack(1, 1.0) + b"x"
        socket.send_frame(frame_payload)
        assert socket.receive()["code"] == "session_expired"


@pytest.mark.parametrize("payload", ["unexpected", b"short", b"x" * 1_048_589])
def test_invalid_frame_closes_connection(
    client: TestClient, payload: bytes | str
) -> None:
    with connect(client) as socket:
        socket.authenticate(AUTH)
        socket.receive()
        socket.send_frame(payload)
        if isinstance(payload, bytes) and len(payload) > 1_048_588:
            with pytest.raises(WebSocketDisconnect):
                socket.receive()
        else:
            assert socket.receive()["code"] == "invalid_frame"


def test_out_of_order_frames_close_connection(client: TestClient) -> None:
    with connect(client) as socket:
        socket.authenticate(AUTH)
        socket.receive()
        frame_payload = FRAME_HEADER.pack(2, 200.0) + b"x"
        socket.send_frame(frame_payload)
        frame_payload = FRAME_HEADER.pack(1, 100.0) + b"x"
        socket.send_frame(frame_payload)
        assert socket.receive()["code"] == "invalid_frame"


def test_unknown_events_close_connection(client: TestClient) -> None:
    with connect(client) as socket:
        socket.authenticate(AUTH)
        socket.receive()
        socket.socket.send_text('42["unexpected",{}]')
        assert socket.receive()["code"] == "invalid_frame"


def test_credentials_are_not_logged(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    token = "private-credential"
    with connect(client) as socket:
        socket.authenticate({"seat_id": 1, "token": token})
        socket.receive()
    assert token not in caplog.text


def test_stream_lifecycle_and_errors_are_logged(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("INFO", logger="modules.streaming.router")
    with connect(client) as socket:
        socket.authenticate(AUTH)
        socket.receive()
        socket.send_frame(b"short")
        assert socket.receive()["code"] == "invalid_frame"

    assert "Stream connected seat_id=1 connection_id=" in caplog.text
    assert "Stream error connection_id=" in caplog.text
    assert "code=invalid_frame" in caplog.text
    assert "Stream disconnected connection_id=" in caplog.text
    assert str(AUTH["token"]) not in caplog.text
