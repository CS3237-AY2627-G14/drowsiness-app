import asyncio
from uuid import uuid4

import pytest

from core.config import Settings
from modules.processing.exceptions import ProcessingException
from modules.processing.inference.frame_buffer import FrameBuffer
from modules.processing.repositories.registry import InMemoryProcessingRegistry
from modules.processing.schemas import (
    DetectionState,
    FrameInput,
    FrameMeasurements,
    QueuedFrame,
)
from modules.processing.services.frame_processing_service import FrameProcessingService
from tests.helpers import MutableTimer


def create_frame_input(frame_id: int, captured_at: float | None = None) -> FrameInput:
    return FrameInput(
        frame_id=frame_id,
        captured_at_ms=float(frame_id * 200) if captured_at is None else captured_at,
        jpeg=b"jpeg",
    )


def test_stale_frames_are_discarded() -> None:
    async def run() -> None:
        timer = MutableTimer()
        processed: list[QueuedFrame] = []

        class RecordingFramePredictor:
            async def predict_batch(
                self,
                batch: tuple[QueuedFrame, ...],
            ) -> tuple[FrameMeasurements, ...]:
                processed.extend(batch)
                return ()

        frame_predictor = RecordingFramePredictor()

        processing_registry = InMemoryProcessingRegistry()
        frame_buffer = FrameBuffer()
        settings = Settings()
        frame_processing_service = FrameProcessingService(
            processing_registry,
            frame_buffer,
            frame_predictor,
            settings,
            timer=timer,
        )
        connection_id = uuid4()
        await frame_processing_service.open_connection(connection_id)
        frame_input = create_frame_input(1)
        await frame_processing_service.submit_frame(connection_id, frame_input)
        timer.current_time = 2.0
        frame_processing_service.start(1)
        try:
            await asyncio.sleep(0.01)
            status = await frame_processing_service.get_status(connection_id)
            assert status.stale_frames == 1 and not status.in_flight
            assert not processed
        finally:
            await frame_processing_service.stop()

    asyncio.run(run())


def test_scheduler_does_not_queue_jobs_or_reuse_closed_history() -> None:
    async def run() -> None:
        started = asyncio.Event()
        finish = asyncio.Event()
        returned = asyncio.Event()
        calls: list[tuple[QueuedFrame, ...]] = []

        class BlockingFramePredictor:
            async def predict_batch(
                self,
                batch: tuple[QueuedFrame, ...],
            ) -> tuple[FrameMeasurements, ...]:
                calls.append(batch)
                started.set()
                await finish.wait()
                returned.set()
                return tuple(
                    FrameMeasurements(
                        connection_id=work.connection_id,
                        frame_id=work.frame.frame_id,
                        captured_at_ms=work.frame.captured_at_ms,
                        fatigue_probability=0.9,
                    )
                    for work in batch
                )

        frame_predictor = BlockingFramePredictor()

        processing_registry = InMemoryProcessingRegistry()
        frame_buffer = FrameBuffer()
        settings = Settings()
        frame_processing_service = FrameProcessingService(
            processing_registry,
            frame_buffer,
            frame_predictor,
            settings,
        )
        frame_processing_service.start(1)
        try:
            connection_id = uuid4()
            await frame_processing_service.open_connection(connection_id)
            frame_input = create_frame_input(1)
            await frame_processing_service.submit_frame(connection_id, frame_input)
            await asyncio.wait_for(started.wait(), 1)
            for index in range(2, 100):
                frame_input = create_frame_input(index)
                await frame_processing_service.submit_frame(connection_id, frame_input)
            status = await frame_processing_service.get_status(connection_id)
            assert (
                status.pending_frames == 1
                and status.in_flight
                and status.replaced_frames == 97
            )
            assert len(calls) == 1
            await frame_processing_service.close_connection(connection_id)
            assert processing_registry.get(connection_id) is None
            assert frame_buffer.pending_count(connection_id) == 0
            assert frame_buffer.is_in_flight(connection_id)
            replacement_id = uuid4()
            await frame_processing_service.open_connection(replacement_id)
            finish.set()
            await asyncio.wait_for(returned.wait(), 1)
            assert processing_registry.get(connection_id) is None
            assert not frame_buffer.is_in_flight(connection_id)
            assert len(calls) == 1
            replacement_status = await frame_processing_service.get_status(
                replacement_id
            )
            assert replacement_status.detection is None
        finally:
            await frame_processing_service.stop()

    asyncio.run(run())


def test_worker_failure_is_reported() -> None:
    async def run() -> None:
        failed = asyncio.Event()

        class FailingFramePredictor:
            async def predict_batch(
                self,
                batch: tuple[QueuedFrame, ...],
            ) -> tuple[FrameMeasurements, ...]:
                failed.set()
                raise RuntimeError("Broken worker")

        frame_predictor = FailingFramePredictor()

        processing_registry = InMemoryProcessingRegistry()
        frame_buffer = FrameBuffer()
        settings = Settings()
        frame_processing_service = FrameProcessingService(
            processing_registry,
            frame_buffer,
            frame_predictor,
            settings,
        )
        frame_processing_service.start(1)
        try:
            connection_id = uuid4()
            await frame_processing_service.open_connection(connection_id)
            frame_input = create_frame_input(1)
            await frame_processing_service.submit_frame(connection_id, frame_input)
            await failed.wait()
            await asyncio.sleep(0)
            with pytest.raises(ProcessingException, match="server_unavailable"):
                await frame_processing_service.get_status(connection_id)
            assert not frame_buffer.is_in_flight(connection_id)
            await frame_processing_service.close_connection(connection_id)
        finally:
            await frame_processing_service.stop()

    asyncio.run(run())


def test_fresh_frame_behind_stale_batch_does_not_wait_for_another_upload() -> None:
    async def run() -> None:
        processing_registry = InMemoryProcessingRegistry()
        frame_buffer = FrameBuffer()
        timer = MutableTimer()
        processed = asyncio.Event()
        batches: list[tuple[QueuedFrame, ...]] = []

        class RecordingFramePredictor:
            async def predict_batch(
                self,
                batch: tuple[QueuedFrame, ...],
            ) -> tuple[FrameMeasurements, ...]:
                batches.append(batch)
                processed.set()
                return ()

        frame_predictor = RecordingFramePredictor()

        settings = Settings()
        frame_processing_service = FrameProcessingService(
            processing_registry,
            frame_buffer,
            frame_predictor,
            settings,
            timer=timer,
        )
        streams = []
        for _ in range(9):
            connection_id = uuid4()
            await frame_processing_service.open_connection(connection_id)
            streams.append(connection_id)
            frame_input = create_frame_input(1)
            await frame_processing_service.submit_frame(connection_id, frame_input)
        timer.current_time = 2.0
        frame_input = create_frame_input(2)
        await frame_processing_service.submit_frame(streams[-1], frame_input)
        frame_processing_service.start(1)
        try:
            await asyncio.wait_for(processed.wait(), 1)
            assert len(batches) == 1
            assert [work.connection_id for work in batches[0]] == [streams[-1]]
            for connection_id in streams[:-1]:
                record = processing_registry.get(connection_id)
                assert record is not None and record.stale_frames == 1
        finally:
            await frame_processing_service.stop()

    asyncio.run(run())


def test_scheduler_failure_is_observed_instead_of_silently_stalling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        failed = asyncio.Event()

        class MeasurementFramePredictor:
            async def predict_batch(
                self,
                batch: tuple[QueuedFrame, ...],
            ) -> tuple[FrameMeasurements, ...]:
                return tuple(
                    FrameMeasurements(
                        connection_id=work.connection_id,
                        frame_id=work.frame.frame_id,
                        captured_at_ms=work.frame.captured_at_ms,
                    )
                    for work in batch
                )

        frame_predictor = MeasurementFramePredictor()

        def fail_evaluation(
            state: DetectionState,
            measurements: FrameMeasurements,
            settings: Settings,
        ) -> DetectionState:
            failed.set()
            raise RuntimeError("Broken detection rule")

        monkeypatch.setattr(
            "modules.processing.services.frame_processing_service.evaluate_measurements",
            fail_evaluation,
        )
        processing_registry = InMemoryProcessingRegistry()
        frame_buffer = FrameBuffer()
        settings = Settings()
        frame_processing_service = FrameProcessingService(
            processing_registry,
            frame_buffer,
            frame_predictor,
            settings,
        )
        frame_processing_service.start(1)
        try:
            connection_id = uuid4()
            await frame_processing_service.open_connection(connection_id)
            frame_input = create_frame_input(1)
            await frame_processing_service.submit_frame(connection_id, frame_input)
            await asyncio.wait_for(failed.wait(), 1)
            await asyncio.sleep(0)
            with pytest.raises(ProcessingException, match="server_unavailable"):
                await frame_processing_service.get_status(connection_id)
        finally:
            await frame_processing_service.stop()

    asyncio.run(run())


@pytest.mark.parametrize("close_before_stop", [False, True])
def test_stopping_processing_releases_inflight_claim(close_before_stop: bool) -> None:
    async def run() -> None:
        started = asyncio.Event()
        finish = asyncio.Event()

        class BlockingFramePredictor:
            async def predict_batch(
                self,
                batch: tuple[QueuedFrame, ...],
            ) -> tuple[FrameMeasurements, ...]:
                started.set()
                await finish.wait()
                return ()

        frame_predictor = BlockingFramePredictor()

        processing_registry = InMemoryProcessingRegistry()
        frame_buffer = FrameBuffer()
        settings = Settings()
        frame_processing_service = FrameProcessingService(
            processing_registry, frame_buffer, frame_predictor, settings
        )
        frame_processing_service.start(1)
        try:
            connection_id = uuid4()
            await frame_processing_service.open_connection(connection_id)
            frame = create_frame_input(1)
            await frame_processing_service.submit_frame(connection_id, frame)
            await asyncio.wait_for(started.wait(), 1)
            assert frame_buffer.is_in_flight(connection_id)
            if close_before_stop:
                await frame_processing_service.close_connection(connection_id)
                assert frame_buffer.is_in_flight(connection_id)
        finally:
            await frame_processing_service.stop()
        assert not frame_buffer.is_in_flight(connection_id)

    asyncio.run(run())
