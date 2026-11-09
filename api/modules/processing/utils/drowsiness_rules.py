from core.config import Settings
from modules.processing.schemas import (
    DetectionSample,
    DetectionState,
    DrowsinessResult,
    FrameMeasurements,
    MinuteSummary,
)

MAX_STREAK_GAP_MS = 1000


def calculate_mean_ear(measurements: FrameMeasurements) -> float | None:
    left_ear = measurements.left_ear
    right_ear = measurements.right_ear
    if left_ear is None or right_ear is None:
        return None
    return (left_ear + right_ear) / 2


def classify_frame(measurements: FrameMeasurements, settings: Settings) -> bool | None:
    if measurements.present is False:
        return None
    if measurements.sensor_drowsy is None:
        return None
    if not measurements.sensor_drowsy:
        return False

    left_ear = measurements.left_ear
    right_ear = measurements.right_ear
    probability = measurements.fatigue_probability
    has_eye_measurements = left_ear is not None and right_ear is not None
    if not has_eye_measurements and probability is None:
        return True
    are_eyes_closed = (
        left_ear is not None
        and right_ear is not None
        and max(left_ear, right_ear) < settings.ear_threshold
    )
    has_fatigue_prediction = (
        probability is not None and probability >= settings.fatigue_threshold
    )
    return are_eyes_closed or has_fatigue_prediction


def update_detection_window(
    samples: tuple[DetectionSample, ...], latest_sample: DetectionSample
) -> tuple[DetectionSample, ...]:
    captured_at_ms = latest_sample.captured_at_ms
    capture_second = int(captured_at_ms // 1000)
    recent_samples = tuple(
        sample
        for sample in samples
        if captured_at_ms - 60000 < sample.captured_at_ms
        and int(sample.captured_at_ms // 1000) < capture_second
    )[-59:]
    return (*recent_samples, latest_sample)


def build_minute_summary(samples: tuple[DetectionSample, ...]) -> MinuteSummary:
    valid_samples = sum(sample.drowsy is not None for sample in samples)
    drowsy_samples = sum(sample.drowsy is True for sample in samples)
    return MinuteSummary(
        valid_samples=valid_samples,
        drowsy_samples=drowsy_samples,
        unavailable_samples=60 - valid_samples,
    )


def expire_detection(
    state: DetectionState, now_ms: float, settings: Settings
) -> DetectionState:
    unknown_since = state.unknown_since_ms
    if (
        state.last_camera_at_ms is not None
        and now_ms - state.last_camera_at_ms > MAX_STREAK_GAP_MS
    ):
        deadline = state.last_camera_at_ms + MAX_STREAK_GAP_MS
        unknown_since = (
            min(unknown_since, deadline) if unknown_since is not None else deadline
        )
    if unknown_since is None:
        return state
    if now_ms - unknown_since >= settings.detection_unknown_timeout_seconds * 1000:
        return state.model_copy(
            update={
                "detection": None,
                "drowsy_since_ms": None,
                "awake_since_ms": None,
                "unknown_since_ms": unknown_since,
            }
        )
    return state.model_copy(
        update={
            "unknown_since_ms": unknown_since,
            "drowsy_since_ms": None,
            "awake_since_ms": None,
        }
    )


def update_detection_transition(
    state: DetectionState,
    measurements: FrameMeasurements,
    settings: Settings,
    now_ms: float,
    *,
    camera_observation: bool,
) -> DetectionState:
    is_drowsy = classify_frame(measurements, settings)
    alert = state.detection.alert if state.detection else False
    drowsy_since = state.drowsy_since_ms
    awake_since = state.awake_since_ms
    unknown_since = state.unknown_since_ms
    camera_at = now_ms if camera_observation else state.last_camera_at_ms
    camera_fresh = camera_at is not None and now_ms - camera_at <= MAX_STREAK_GAP_MS
    if measurements.present is False:
        alert, drowsy_since, awake_since, unknown_since = False, None, None, None
    elif is_drowsy is None or not camera_fresh:
        drowsy_since, awake_since = None, None
        if unknown_since is None:
            unknown_since = now_ms
    else:
        unknown_since = None
        if is_drowsy:
            awake_since = None
            drowsy_since = now_ms if drowsy_since is None else drowsy_since
            if (
                camera_observation
                and now_ms - drowsy_since >= settings.drowsy_streak_seconds * 1000
            ):
                alert = True
        else:
            drowsy_since = None
            awake_since = now_ms if awake_since is None else awake_since
            if (
                camera_observation
                and now_ms - awake_since >= settings.awake_streak_seconds * 1000
            ):
                alert = False
    detection = (
        state.detection.model_copy(update={"alert": alert}) if state.detection else None
    )
    updated = state.model_copy(
        update={
            "detection": detection,
            "drowsy_since_ms": drowsy_since,
            "awake_since_ms": awake_since,
            "unknown_since_ms": unknown_since,
            "last_camera_at_ms": camera_at,
        }
    )
    return expire_detection(updated, now_ms, settings)


def evaluate_measurements(
    state: DetectionState,
    measurements: FrameMeasurements,
    settings: Settings,
    *,
    now_ms: float | None = None,
) -> DetectionState:
    """Classify a frame and update its camera's minute summary and alert."""
    now_ms = measurements.captured_at_ms if now_ms is None else now_ms
    state = expire_detection(state, now_ms, settings)
    mean_ear = calculate_mean_ear(measurements)
    is_drowsy = classify_frame(measurements, settings)
    latest_sample = DetectionSample(
        captured_at_ms=measurements.captured_at_ms, drowsy=is_drowsy
    )
    samples = update_detection_window(state.samples, latest_sample)
    minute = build_minute_summary(samples)
    alert = state.detection.alert if state.detection else False
    detection = DrowsinessResult(
        frame_id=measurements.frame_id,
        captured_at_ms=measurements.captured_at_ms,
        ear=mean_ear,
        fatigue_probability=measurements.fatigue_probability,
        sensor_drowsy=measurements.sensor_drowsy,
        present=measurements.present,
        minute=minute,
        processing_ms=measurements.processing_ms,
        alert=alert,
        sensor_score=measurements.sensor_score,
        sensor_model_version=measurements.sensor_model_version,
        sensor_unavailable_reason=measurements.sensor_unavailable_reason,
    )
    updated = state.model_copy(update={"samples": samples, "detection": detection})
    return update_detection_transition(
        updated, measurements, settings, now_ms, camera_observation=True
    )


def reclassify_latest_sample(
    state: DetectionState,
    measurements: FrameMeasurements,
    settings: Settings,
    *,
    now_ms: float | None = None,
) -> DetectionState:
    """Replace the latest sample's decision without appending another sample."""
    now_ms = measurements.captured_at_ms if now_ms is None else now_ms
    state = expire_detection(state, now_ms, settings)
    detection = state.detection
    if not state.samples or detection is None:
        return state
    latest_sample = state.samples[-1]
    is_drowsy = classify_frame(measurements, settings)
    samples = (
        *state.samples[:-1],
        DetectionSample(captured_at_ms=latest_sample.captured_at_ms, drowsy=is_drowsy),
    )
    minute = build_minute_summary(samples)
    updated_detection = detection.model_copy(
        update={
            "sensor_drowsy": measurements.sensor_drowsy,
            "present": measurements.present,
            "sensor_score": measurements.sensor_score,
            "sensor_model_version": measurements.sensor_model_version,
            "sensor_unavailable_reason": measurements.sensor_unavailable_reason,
            "minute": minute,
        }
    )
    updated = state.model_copy(
        update={"samples": samples, "detection": updated_detection}
    )
    return update_detection_transition(
        updated, measurements, settings, now_ms, camera_observation=False
    )
