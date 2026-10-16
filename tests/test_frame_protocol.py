import pytest

from modules.processing.facade import FrameInput
from modules.streaming.schemas import StreamError
from modules.streaming.utils.parse_frame import FRAME_HEADER, parse_frame


@pytest.mark.parametrize(
    "payload",
    [
        None,
        "not binary",
        {},
        b"",
        b"short",
        FRAME_HEADER.pack(0, 0.0) + b"x",
        FRAME_HEADER.pack(1, float("nan")) + b"x",
        FRAME_HEADER.pack(1, -1.0) + b"x",
        FRAME_HEADER.pack(1, 1.0) + b"x" * 11,
    ],
)
def test_invalid_binary_frames(payload: object) -> None:
    with pytest.raises(StreamError):
        parse_frame(payload, 10)


def test_binary_header_roundtrip() -> None:
    payload = FRAME_HEADER.pack(42, 1234.5) + b"jpeg"
    parsed = parse_frame(payload, 10)
    assert parsed == FrameInput(frame_id=42, captured_at_ms=1234.5, jpeg=b"jpeg")
