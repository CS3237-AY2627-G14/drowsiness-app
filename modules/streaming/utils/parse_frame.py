import math
import struct

from modules.processing.facade import FrameInput
from modules.streaming.schemas import StreamError

FRAME_HEADER = struct.Struct("!Id")


def parse_frame(payload: object, max_frame_bytes: int) -> FrameInput:
    if not isinstance(payload, bytes):
        raise StreamError("invalid_frame")
    if not FRAME_HEADER.size < len(payload) <= max_frame_bytes + FRAME_HEADER.size:
        raise StreamError("invalid_frame")
    frame_id, captured_at_ms = FRAME_HEADER.unpack_from(payload)
    if frame_id == 0 or not math.isfinite(captured_at_ms) or captured_at_ms < 0:
        raise StreamError("invalid_frame")
    return FrameInput(
        frame_id=frame_id,
        captured_at_ms=captured_at_ms,
        jpeg=payload[FRAME_HEADER.size :],
    )
