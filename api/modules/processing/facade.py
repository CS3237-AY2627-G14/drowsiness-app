import time
from uuid import UUID

from modules.processing.calibration.schemas import RawTelemetry
from modules.processing.calibration.service import CalibrationService
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
    def __init__(
        self,
        frame_processing_service: FrameProcessingService,
        calibration_service: CalibrationService | None = None,
    ) -> None:
        self._frame_processing_service = frame_processing_service
        self._calibration_service = calibration_service
        self._latest_telemetry: dict[int, RawTelemetry] = {}
        self._retired_boots: dict[int, set[str]] = {}

    async def submit_raw_telemetry(
        self, telemetry: RawTelemetry, seat_id: int = 1
    ) -> None:
        if seat_id == 1 and self._calibration_service is not None:
            if not await self._calibration_service.receive(telemetry):
                return
            evidence = self._calibration_service.evidence()
            self._calibration_service.observe_sensor_update()
        else:
            previous = self._latest_telemetry.get(seat_id)
            retired = self._retired_boots.setdefault(seat_id, set())
            if telemetry.boot_id in retired:
                return
            if previous is not None:
                if previous.boot_id == telemetry.boot_id:
                    if (
                        telemetry.sequence <= previous.sequence
                        or telemetry.uptime_ms <= previous.uptime_ms
                    ):
                        return
                else:
                    retired.add(previous.boot_id)
            self._latest_telemetry[seat_id] = telemetry
            from modules.processing.services.sensor_classification import (
                classify_raw_telemetry,
            )

            evidence = classify_raw_telemetry(telemetry, time.time_ns() / 1_000_000)
        await self._frame_processing_service.submit_sensor_measurements(
            seat_id, evidence
        )

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
