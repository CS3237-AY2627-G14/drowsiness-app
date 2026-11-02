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
            sensor_drowsy=result.sensor_drowsy,
            present=result.present,
            minute=result.minute,
            alert=result.alert,
            face_detected=result.face_detected,
            sensor_score=result.sensor_score,
            sensor_model_version=result.sensor_model_version,
            sensor_unavailable_reason=result.sensor_unavailable_reason,
        )
    return StreamResponse(
        detection=detection,
        diagnostics=status.diagnostics if diagnostics else None,
        mqtt_alert_sent_recently=status.mqtt_alert_sent_recently,
    )
