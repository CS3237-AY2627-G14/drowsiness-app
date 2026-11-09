from uuid import UUID

from modules.processing.exceptions import ProcessingException
from modules.processing.schemas import (
    CameraObservation,
    DetectionDebug,
    DetectionState,
    DrowsinessResult,
    FrameInput,
    FrameMeasurements,
    LiveTelemetry,
    MinuteSummary,
    ProcessingStatus,
    RawTelemetry,
    SensorMeasurements,
    SensorUpdate,
    StoredSample,
)
from modules.processing.sensor_features import (
    advance_sensor_window,
    baseline_result,
    extract_features,
)
from modules.processing.services.frame_processing_service import FrameProcessingService
from modules.processing.utils.drowsiness_rules import (
    classify_frame,
    evaluate_measurements,
    reclassify_latest_sample,
)

__all__ = [
    "advance_sensor_window",
    "RawTelemetry",
    "StoredSample",
    "CameraObservation",
    "SensorUpdate",
    "LiveTelemetry",
    "FrameMeasurements",
    "DetectionState",
    "DetectionDebug",
    "extract_features",
    "baseline_result",
    "classify_frame",
    "evaluate_measurements",
    "reclassify_latest_sample",
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

    async def submit_raw_telemetry(
        self, telemetry: RawTelemetry, seat_id: int = 1
    ) -> None:
        await self._frame_processing_service.submit_raw_telemetry(telemetry, seat_id)

    def get_live_telemetry(self) -> LiveTelemetry:
        return self._frame_processing_service.get_live_telemetry()

    def get_sensor_evidence(self) -> SensorMeasurements:
        return self._frame_processing_service.get_sensor_evidence()

    async def activate_sensor_model(self, model_id: str | None) -> None:
        await self._frame_processing_service.activate_sensor_model(model_id)

    async def select_candidate_model(self, model_id: str) -> None:
        await self._frame_processing_service.select_candidate_model(model_id)

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
