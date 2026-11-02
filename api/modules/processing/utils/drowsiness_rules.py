from core.config import Settings
from modules.processing.schemas import (
    DetectionSample,
    DetectionState,
    DrowsinessResult,
    FrameMeasurements,
    MinuteSummary,
)

ALERT_MIN_VALID_SAMPLES = 10


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


def should_raise_alert(minute: MinuteSummary) -> bool:
    return (
        minute.valid_samples >= ALERT_MIN_VALID_SAMPLES
        and minute.drowsy_samples * 2 >= minute.valid_samples
    )


def evaluate_measurements(
    state: DetectionState, measurements: FrameMeasurements, settings: Settings
) -> DetectionState:
    """Classify a frame and update its camera's minute summary and alert."""
    mean_ear = calculate_mean_ear(measurements)
    is_drowsy = classify_frame(measurements, settings)
    latest_sample = DetectionSample(
        captured_at_ms=measurements.captured_at_ms, drowsy=is_drowsy
    )
    samples = update_detection_window(state.samples, latest_sample)
    minute = build_minute_summary(samples)
    alert = should_raise_alert(minute)
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
    )
    return DetectionState(samples=samples, detection=detection)


def reclassify_latest_sample(
    state: DetectionState, measurements: FrameMeasurements, settings: Settings
) -> DetectionState:
    """Replace the latest sample's decision without appending another sample."""
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
            "minute": minute,
            "alert": should_raise_alert(minute),
        }
    )
    return DetectionState(samples=samples, detection=updated_detection)
