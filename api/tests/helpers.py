from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

from core.clock import MonotonicTimer, Timer
from core.config import Settings
from modules.classrooms.facade import ClassroomsFacade, SeatInfo
from modules.classrooms.fixtures import create_demo_classroom
from modules.classrooms.repositories.room_repository import InMemoryRoomRepository
from modules.classrooms.repositories.seat_repository import InMemorySeatRepository
from modules.classrooms.service import ClassroomsService
from modules.processing.facade import ProcessingFacade
from modules.processing.inference import InferenceRuntime
from modules.processing.inference.frame_buffer import FrameBuffer
from modules.processing.inference.frame_predictor import FramePredictor
from modules.processing.repositories.registry import InMemoryProcessingRegistry
from modules.processing.schemas import FrameMeasurements, QueuedFrame
from modules.processing.services.frame_processing_service import (
    FrameProcessingService,
)
from modules.sessions.facade import SessionsFacade
from modules.sessions.fixtures import create_demo_sessions
from modules.sessions.repositories.publisher_repository import (
    InMemoryPublisherRepository,
)
from modules.sessions.repositories.stream_session_repository import (
    InMemoryStreamSessionRepository,
)
from modules.sessions.schemas import StreamSessionRecord
from modules.sessions.service import SessionsService
from modules.streaming.repositories.registry import InMemoryStreamingRegistry
from modules.streaming.service import StreamingService


@dataclass
class MutableClock:
    current_time: datetime = datetime(2026, 10, 14, tzinfo=UTC)

    def now(self) -> datetime:
        return self.current_time


@dataclass
class MutableTimer:
    current_time: float = 0.0

    def now(self) -> float:
        return self.current_time


def build_classrooms(seats: list[SeatInfo] | None = None) -> ClassroomsFacade:
    rooms, default_seats = create_demo_classroom()
    classroom_seats = default_seats if seats is None else seats
    room_repository = InMemoryRoomRepository(rooms)
    seat_repository = InMemorySeatRepository(classroom_seats)
    classrooms_service = ClassroomsService(room_repository, seat_repository)
    return ClassroomsFacade(classrooms_service)


def build_sessions(
    clock: MutableClock,
    *,
    sessions: list[StreamSessionRecord] | None = None,
    seats: list[SeatInfo] | None = None,
) -> SessionsFacade:
    _, default_seats = create_demo_classroom()
    records = sessions
    if records is None:
        created_at = clock.now()
        records = create_demo_sessions(
            default_seats, created_at=created_at, ttl_seconds=7200
        )
    stream_session_repository = InMemoryStreamSessionRepository(records)
    publisher_repository = InMemoryPublisherRepository()
    classrooms_facade = build_classrooms(seats)
    sessions_service = SessionsService(
        stream_session_repository,
        publisher_repository,
        classrooms_facade,
        clock,
        max_publishers=250,
    )
    return SessionsFacade(sessions_service)


class FakeFramePredictor:
    async def predict_batch(
        self,
        batch: tuple[QueuedFrame, ...],
    ) -> tuple[FrameMeasurements, ...]:
        return tuple(
            FrameMeasurements(
                connection_id=work.connection_id,
                frame_id=work.frame.frame_id,
                captured_at_ms=work.frame.captured_at_ms,
                left_ear=0.3,
                right_ear=0.3,
                fatigue_probability=0.1,
            )
            for work in batch
        )


@asynccontextmanager
async def fake_inference_runtime(settings: Settings) -> AsyncIterator[InferenceRuntime]:
    yield InferenceRuntime(FakeFramePredictor(), 1)


@dataclass
class StreamingRuntime:
    sessions_facade: SessionsFacade
    frame_processing_service: FrameProcessingService
    processing_registry: InMemoryProcessingRegistry
    frame_buffer: FrameBuffer
    streaming_service: StreamingService
    streaming_registry: InMemoryStreamingRegistry


def build_streaming_runtime(
    clock: MutableClock,
    *,
    timer: Timer | None = None,
    frame_predictor: FramePredictor | None = None,
) -> StreamingRuntime:
    sessions_facade = build_sessions(clock)
    selected_frame_predictor = (
        frame_predictor if frame_predictor is not None else FakeFramePredictor()
    )
    selected_timer = timer if timer is not None else MonotonicTimer()
    processing_registry = InMemoryProcessingRegistry()
    frame_buffer = FrameBuffer()
    settings = Settings()
    frame_processing_service = FrameProcessingService(
        processing_registry,
        frame_buffer,
        selected_frame_predictor,
        settings,
        timer=selected_timer,
    )
    processing_facade = ProcessingFacade(frame_processing_service)
    streaming_registry = InMemoryStreamingRegistry()
    streaming_service = StreamingService(
        streaming_registry, sessions_facade, processing_facade, timer=selected_timer
    )
    return StreamingRuntime(
        sessions_facade,
        frame_processing_service,
        processing_registry,
        frame_buffer,
        streaming_service,
        streaming_registry,
    )
