from uuid import UUID

from modules.processing.exceptions import ProcessingException
from modules.processing.schemas import (
    DrowsinessResult,
    FrameInput,
    MinuteSummary,
    ProcessingStatus,
    SensorMeasurements,
)
from modules.processing.services.frame_processing_service import FrameProcessingService

__all__ = [
    "DrowsinessResult",
    "FrameInput",
    "MinuteSummary",
    "ProcessingException",
    "ProcessingFacade",
    "ProcessingStatus",
    "SensorMeasurements",
]


class ProcessingFacade:
    def __init__(self, frame_processing_service: FrameProcessingService) -> None:
        self._frame_processing_service = frame_processing_service

    async def open_connection(self, connection_id: UUID) -> None:
        await self._frame_processing_service.open_connection(connection_id)

    async def associate_seat(self, connection_id: UUID, seat_id: int) -> None:
        await self._frame_processing_service.associate_seat(connection_id, seat_id)

    async def submit_sensor_measurements(
        self, seat_id: int, measurements: SensorMeasurements
    ) -> None:
        await self._frame_processing_service.submit_sensor_measurements(
            seat_id, measurements
        )

    async def submit_frame(self, connection_id: UUID, frame: FrameInput) -> None:
        await self._frame_processing_service.submit_frame(connection_id, frame)

    async def get_status(self, connection_id: UUID) -> ProcessingStatus:
        return await self._frame_processing_service.get_status(connection_id)

    async def close_connection(self, connection_id: UUID) -> None:
        await self._frame_processing_service.close_connection(connection_id)
