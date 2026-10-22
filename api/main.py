from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

import socketio
from fastapi import FastAPI

from core.clock import Clock, SystemClock
from core.config import Settings
from core.logging import configure_logging
from modules.classrooms.facade import ClassroomsFacade, SeatInfo
from modules.classrooms.fixtures import create_demo_classroom
from modules.classrooms.repositories.room_repository import InMemoryRoomRepository
from modules.classrooms.repositories.seat_repository import InMemorySeatRepository
from modules.classrooms.router import router as classrooms_router
from modules.classrooms.service import ClassroomsService
from modules.processing.facade import ProcessingFacade
from modules.processing.inference import InferenceRuntime, create_inference_runtime
from modules.processing.inference.frame_buffer import FrameBuffer
from modules.processing.mqtt_router import SensorMqttRouter
from modules.processing.repositories.registry import InMemoryProcessingRegistry
from modules.processing.services.frame_processing_service import FrameProcessingService
from modules.sessions.facade import SessionsFacade
from modules.sessions.fixtures import create_demo_sessions
from modules.sessions.repositories.publisher_repository import (
    InMemoryPublisherRepository,
)
from modules.sessions.repositories.stream_session_repository import (
    InMemoryStreamSessionRepository,
)
from modules.sessions.service import SessionsService
from modules.streaming.facade import StreamingFacade
from modules.streaming.repositories.registry import InMemoryStreamingRegistry
from modules.streaming.router import StreamingSocketRouter
from modules.streaming.service import StreamingService
from modules.streaming.utils.parse_frame import FRAME_HEADER

type InferenceFactory = Callable[
    [Settings], AbstractAsyncContextManager[InferenceRuntime]
]


def build_classrooms(
    configuration: Settings,
) -> tuple[ClassroomsFacade, list[SeatInfo]]:
    rooms, seats = create_demo_classroom(configuration.demo_seat_count)
    room_repository = InMemoryRoomRepository(rooms)
    seat_repository = InMemorySeatRepository(seats)
    classrooms_service = ClassroomsService(room_repository, seat_repository)
    return ClassroomsFacade(classrooms_service), seats


def build_sessions(
    configuration: Settings,
    classrooms_facade: ClassroomsFacade,
    seats: list[SeatInfo],
    clock: Clock,
) -> SessionsFacade:
    created_at = clock.now()
    sessions = create_demo_sessions(
        seats,
        created_at=created_at,
        ttl_seconds=configuration.demo_session_ttl_seconds,
    )
    stream_session_repository = InMemoryStreamSessionRepository(sessions)
    publisher_repository = InMemoryPublisherRepository()
    sessions_service = SessionsService(
        stream_session_repository,
        publisher_repository,
        classrooms_facade,
        clock,
        configuration.max_publishers,
    )
    return SessionsFacade(sessions_service)


def build_streaming(
    configuration: Settings,
    socket_server: socketio.AsyncServer,
    sessions_facade: SessionsFacade,
    inference_runtime: InferenceRuntime,
) -> tuple[StreamingSocketRouter, FrameProcessingService, ProcessingFacade]:
    processing_registry = InMemoryProcessingRegistry()
    frame_buffer = FrameBuffer()
    frame_processing_service = FrameProcessingService(
        processing_registry,
        frame_buffer,
        inference_runtime.frame_predictor,
        configuration,
    )
    processing_facade = ProcessingFacade(frame_processing_service)
    streaming_registry = InMemoryStreamingRegistry()
    streaming_service = StreamingService(
        streaming_registry, sessions_facade, processing_facade
    )
    streaming_facade = StreamingFacade(streaming_service)
    streaming_socket_router = StreamingSocketRouter(
        socket_server, streaming_facade, configuration
    )
    return streaming_socket_router, frame_processing_service, processing_facade


def create_app(
    settings: Settings | None = None,
    *,
    clock: Clock | None = None,
    inference_factory: InferenceFactory = create_inference_runtime,
) -> FastAPI:
    configure_logging()
    application_clock = clock if clock is not None else SystemClock()
    configuration = settings if settings is not None else Settings()
    socket_server = socketio.AsyncServer(
        async_mode="asgi",
        # One event at a time per client, so frame admission stays in arrival order.
        async_handlers=False,
        cors_allowed_origins=list(configuration.allowed_origins),
        transports=["websocket"],
        max_http_buffer_size=configuration.max_frame_bytes + FRAME_HEADER.size,
        logger=False,
        engineio_logger=False,
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        classrooms_facade, seats = build_classrooms(configuration)
        sessions_facade = build_sessions(
            configuration, classrooms_facade, seats, application_clock
        )
        application.state.classrooms_facade = classrooms_facade
        async with inference_factory(configuration) as inference_runtime:
            (
                streaming_socket_router,
                frame_processing_service,
                processing_facade,
            ) = build_streaming(
                configuration, socket_server, sessions_facade, inference_runtime
            )
            sensor_mqtt_router = SensorMqttRouter(configuration, processing_facade)
            try:
                frame_processing_service.start(inference_runtime.workers)
                sensor_mqtt_router.start()
                yield
            finally:
                try:
                    await sensor_mqtt_router.stop()
                finally:
                    try:
                        await streaming_socket_router.stop()
                    finally:
                        await frame_processing_service.stop()

    application = FastAPI(title="Drowsiness API", lifespan=lifespan)
    application.include_router(classrooms_router)
    socket_application = socketio.ASGIApp(socket_server, socketio_path=None)
    application.mount("/api/socket.io", socket_application)

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()
