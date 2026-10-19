from uuid import UUID, uuid4

from modules.processing.inference.frame_buffer import FrameBuffer
from modules.processing.schemas import FrameInput, QueuedFrame


def create_work(connection_id: UUID, frame_id: int) -> QueuedFrame:
    frame = FrameInput(frame_id=frame_id, captured_at_ms=float(frame_id), jpeg=b"jpeg")
    return QueuedFrame(connection_id=connection_id, frame=frame, received_at=0.0)


def test_replacement_preserves_fairness_and_inflight_bound() -> None:
    buffer = FrameBuffer()
    first_camera, second_camera = uuid4(), uuid4()
    first_work = create_work(first_camera, 1)
    second_work = create_work(second_camera, 1)
    assert not buffer.put_latest(first_work)
    assert not buffer.put_latest(second_work)
    latest_work = create_work(first_camera, 2)
    assert buffer.put_latest(latest_work)
    batch = buffer.claim_batch(1)
    assert batch == (latest_work,)
    following_work = create_work(first_camera, 3)
    assert not buffer.put_latest(following_work)
    assert buffer.claim_batch(8) == (second_work,)
    assert buffer.pending_count(first_camera) == 1
    assert buffer.is_in_flight(first_camera)
    assert buffer.claim_batch(8) == ()
    buffer.release_batch(batch)
    assert buffer.claim_batch(8) == (following_work,)


def test_discard_pending_preserves_inflight_claim() -> None:
    buffer = FrameBuffer()
    connection_id = uuid4()
    work = create_work(connection_id, 1)
    buffer.put_latest(work)
    batch = buffer.claim_batch(1)
    pending_work = create_work(connection_id, 2)
    buffer.put_latest(pending_work)
    buffer.discard_pending(connection_id)
    buffer.discard_pending(connection_id)
    assert buffer.pending_count(connection_id) == 0
    assert buffer.is_in_flight(connection_id)
    buffer.release_batch(batch)
    assert not buffer.is_in_flight(connection_id)
    assert buffer.claim_batch(1) == ()
