from typing import Any
from uuid import UUID

from core.config import Settings
from modules.processing.calibration.schemas import RecordingDetail
from modules.processing.schemas import DetectionState
from modules.processing.utils.drowsiness_rules import (
    classify_frame,
    evaluate_measurements,
    reclassify_latest_sample,
)


def summarize_rehearsal(detail: RecordingDetail, settings: Settings) -> dict[str, Any]:
    results: dict[str, Any] = {}
    awake_seconds = sum(
        item.end - item.start for item in detail.intervals if item.label == "awake"
    )
    for name in ("active", "baseline", "candidate"):
        state = DetectionState()
        false_alerts = 0
        onsets: list[float] = []
        models: set[str] = set()
        previous_source: tuple[UUID, str | None, int] | None = None
        valid_observations = 0
        for observation in detail.observations:
            sensor = observation.sensors.get(name)
            if sensor is None:
                continue
            if sensor.model_version:
                models.add(sensor.model_version)
            source = (
                observation.frame.connection_id,
                sensor.model_version,
                observation.generation,
            )
            if source != previous_source:
                state = DetectionState()
                previous_source = source
            previous_alert = state.detection.alert if state.detection else False
            frame = observation.frame.model_copy(
                update={
                    "captured_at_ms": observation.received_at * 1000,
                    "sensor_drowsy": sensor.drowsy,
                    "present": sensor.present,
                }
            )
            state = evaluate_measurements(state, frame, settings)
            valid_observations += int(classify_frame(frame, settings) is not None)
            if state.detection and state.detection.alert and not previous_alert:
                onsets.append(observation.received_at)
                if any(
                    item.label == "awake"
                    and item.start <= observation.received_at < item.end
                    for item in detail.intervals
                ):
                    false_alerts += 1
            for update in observation.sensor_updates:
                revised_sensor = update.sensors.get(name)
                if revised_sensor is None:
                    continue
                previous_alert = state.detection.alert if state.detection else False
                revised = frame.model_copy(
                    update={
                        "sensor_drowsy": revised_sensor.drowsy,
                        "present": revised_sensor.present,
                    }
                )
                previous_valid = classify_frame(frame, settings) is not None
                valid_observations += int(
                    classify_frame(revised, settings) is not None
                ) - int(previous_valid)
                frame = revised
                state = reclassify_latest_sample(state, revised, settings)
                if state.detection and state.detection.alert and not previous_alert:
                    onsets.append(update.received_at)
                    if any(
                        item.label == "awake"
                        and item.start <= update.received_at < item.end
                        for item in detail.intervals
                    ):
                        false_alerts += 1
        latencies = [
            next(
                (
                    time - interval.start
                    for time in onsets
                    if interval.start <= time < interval.end
                ),
                None,
            )
            for interval in detail.intervals
            if interval.label == "drowsy"
        ]
        results[name] = {
            "false_alert_activations": false_alerts,
            "false_alerts_per_awake_minute": false_alerts / (awake_seconds / 60)
            if awake_seconds
            else None,
            "alert_latency_seconds_by_drowsy_episode": latencies,
            "model_versions": sorted(models),
            "valid_observations": valid_observations,
        }
    return {
        "camera_observations": len(detail.observations),
        "awake_minutes": awake_seconds / 60,
        "comparisons": results,
        "note": (
            "Replayed one observation per server receipt second with sensor updates. "
            "This diagnostic is not an exact live trace. "
            "Missing latencies mean no new alert in that episode. No images are stored."
        ),
    }
