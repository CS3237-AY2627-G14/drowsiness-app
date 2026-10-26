from modules.streaming.schemas import (
    DetectionSnapshot,
    StreamResponse,
    StreamStatus,
)


def build_stream_response(status: StreamStatus, diagnostics: bool) -> StreamResponse:
    detection = None
    if status.detection is not None:
        result = status.detection
        detection = DetectionSnapshot(
            captured_at_ms=result.captured_at_ms,
            ear=result.ear,
            fatigue_probability=result.fatigue_probability,
            fsr_raw=result.fsr_raw,
            tof_distance_mm=result.tof_distance_mm,
            present=result.present,
            minute=result.minute,
            alert=result.alert,
            face_detected=result.face_detected,
        )
    return StreamResponse(
        detection=detection,
        diagnostics=status.diagnostics if diagnostics else None,
        mqtt_alert_sent_recently=status.mqtt_alert_sent_recently,
    )
