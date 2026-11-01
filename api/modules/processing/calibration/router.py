import asyncio
import csv
import io
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response, StreamingResponse

from modules.processing.calibration.facade import CalibrationFacade
from modules.processing.calibration.schemas import (
    LabelInterval,
    LiveTelemetry,
    ModelRequest,
    Recording,
    RecordingDetail,
    RecordingRequest,
    TrainingJob,
    TrainingRequest,
)

router = APIRouter(prefix="/api/calibration", tags=["calibration"])


def get_processing(request: Request) -> CalibrationFacade:
    return request.app.state.calibration_facade  # type: ignore[no-any-return]


Processing = Annotated[CalibrationFacade, Depends(get_processing)]


@router.get("/live")
async def live(processing: Processing) -> LiveTelemetry:
    return processing.live()


@router.get("/events")
async def events(request: Request, processing: Processing) -> StreamingResponse:
    async def stream() -> AsyncIterator[str]:
        while not await request.is_disconnected():
            yield f"data: {processing.live().model_dump_json()}\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/recordings")
async def recordings(processing: Processing) -> list[Recording]:
    return await processing.list_recordings()


@router.post("/recordings", status_code=201)
async def start_recording(body: RecordingRequest, processing: Processing) -> Recording:
    return await processing.start_recording(body)


@router.post("/recordings/{recording_id}/stop")
async def stop_recording(recording_id: str, processing: Processing) -> Recording:
    return await processing.stop_recording(recording_id)


@router.get("/recordings/{recording_id}")
async def detail(recording_id: str, processing: Processing) -> RecordingDetail:
    return await processing.detail(recording_id)


@router.put("/recordings/{recording_id}/labels", status_code=204)
async def label(
    recording_id: str, body: list[LabelInterval], processing: Processing
) -> None:
    await processing.label(recording_id, body)


@router.get("/recordings/{recording_id}/export")
async def export(recording_id: str, processing: Processing) -> Response:
    data = await processing.detail(recording_id)
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
async def models(processing: Processing) -> list[TrainingJob]:
    return await processing.jobs()


@router.post("/training", status_code=202)
async def train(body: TrainingRequest, processing: Processing) -> TrainingJob:
    return await processing.train(body.recording_ids)


@router.post("/selection", status_code=204)
async def activate(body: ModelRequest, processing: Processing) -> None:
    await processing.activate(body.model_id)


@router.get("/recordings/{recording_id}/rehearsal")
async def rehearsal(recording_id: str, processing: Processing) -> dict[str, Any]:
    return await processing.rehearsal(recording_id)
