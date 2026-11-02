import asyncio
import csv
import io
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response, StreamingResponse

from modules.calibration.facade import CalibrationFacade
from modules.calibration.schemas import (
    LabelInterval,
    ModelRequest,
    Recording,
    RecordingDetail,
    RecordingRequest,
    TrainingJob,
    TrainingRequest,
)
from modules.processing.facade import LiveTelemetry

router = APIRouter(prefix="/api/calibration", tags=["calibration"])


def get_calibration_facade(request: Request) -> CalibrationFacade:
    return request.app.state.calibration_facade  # type: ignore[no-any-return]


Calibration = Annotated[CalibrationFacade, Depends(get_calibration_facade)]


@router.get("/live")
async def get_live_telemetry(calibration_facade: Calibration) -> LiveTelemetry:
    return calibration_facade.get_live_telemetry()


@router.get("/events")
async def events(
    request: Request, calibration_facade: Calibration
) -> StreamingResponse:
    async def stream() -> AsyncIterator[str]:
        while not await request.is_disconnected():
            telemetry = calibration_facade.get_live_telemetry()
            payload = telemetry.model_dump_json()
            yield f"data: {payload}\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/recordings")
async def recordings(calibration_facade: Calibration) -> list[Recording]:
    return await calibration_facade.list_recordings()


@router.post("/recordings", status_code=201)
async def start_recording(
    body: RecordingRequest, calibration_facade: Calibration
) -> Recording:
    return await calibration_facade.start_recording(body)


@router.post("/recordings/{recording_id}/stop")
async def stop_recording(
    recording_id: str, calibration_facade: Calibration
) -> Recording:
    return await calibration_facade.stop_recording(recording_id)


@router.get("/recordings/{recording_id}")
async def get_recording(
    recording_id: str, calibration_facade: Calibration
) -> RecordingDetail:
    return await calibration_facade.get_recording(recording_id)


@router.put("/recordings/{recording_id}/labels", status_code=204)
async def replace_labels(
    recording_id: str, body: list[LabelInterval], calibration_facade: Calibration
) -> None:
    await calibration_facade.replace_labels(recording_id, body)


@router.get("/recordings/{recording_id}/export")
async def export(recording_id: str, calibration_facade: Calibration) -> Response:
    data = await calibration_facade.get_recording(recording_id)
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        [
            "received_at",
            "boot_id",
            "sequence",
            "uptime_ms",
            "upper_cm",
            "lower_mm",
            "back_adc",
            "desk_adc",
            "label",
            "posture",
            "provenance",
        ]
    )
    for sample in data.samples:
        raw = sample.telemetry
        interval = next(
            (
                item
                for item in data.intervals
                if item.start <= sample.received_at < item.end
            ),
            None,
        )
        writer.writerow(
            [
                sample.received_at,
                raw.boot_id,
                raw.sequence,
                raw.uptime_ms,
                raw.upper_cm,
                raw.lower_mm,
                raw.back_adc,
                raw.desk_adc,
                interval.label if interval else "",
                interval.posture if interval else "",
                "staged_posture",
            ]
        )
    return Response(
        output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="sensor-recording.csv"'},
    )


@router.get("/models")
async def models(calibration_facade: Calibration) -> list[TrainingJob]:
    return await calibration_facade.list_training_jobs()


@router.post("/training", status_code=202)
async def train_candidate(
    body: TrainingRequest, calibration_facade: Calibration
) -> TrainingJob:
    return await calibration_facade.train_candidate(body.recording_ids)


@router.post("/selection", status_code=204)
async def activate_model(body: ModelRequest, calibration_facade: Calibration) -> None:
    await calibration_facade.activate_model(body.model_id)


@router.get("/recordings/{recording_id}/rehearsal")
async def get_rehearsal_report(
    recording_id: str, calibration_facade: Calibration
) -> dict[str, Any]:
    return await calibration_facade.get_rehearsal_report(recording_id)
