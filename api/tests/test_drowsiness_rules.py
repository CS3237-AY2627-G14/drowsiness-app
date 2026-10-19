from uuid import uuid4

import pytest

from core.config import Settings
from modules.processing.schemas import DetectionState, FrameMeasurements
from modules.processing.utils.drowsiness_rules import evaluate_measurements


def observe(
    record: DetectionState,
    captured_at_ms: float,
    left: float | None = 0.3,
    right: float | None = 0.3,
    probability: float | None = 0.1,
) -> DetectionState:
    measurements = FrameMeasurements(
        connection_id=uuid4(),
        frame_id=record.detection.frame_id + 1 if record.detection is not None else 1,
        captured_at_ms=captured_at_ms,
        left_ear=left,
        right_ear=right,
        fatigue_probability=probability,
    )
    settings = Settings()
    return evaluate_measurements(record, measurements, settings)


def test_minute_alert_requires_30_valid_samples_and_at_least_half_drowsy() -> None:
    record = DetectionState()
    for index in range(30):
        probability = 0.9 if index < 15 else 0.1
        record = observe(
            record, float(index * 1400 + (index % 3) * 20), probability=probability
        )
        assert record.detection is not None
        if index < 29:
            assert not record.detection.alert
    assert record.detection is not None
    assert record.detection.minute.valid_samples == 30
    assert record.detection.minute.drowsy_samples == 15
    assert record.detection.minute.unavailable_samples == 30
    assert record.detection.alert
    record = observe(record, 43000.0)
    assert record.detection is not None and not record.detection.alert


def test_missing_observations_are_unknown_and_old_samples_expire() -> None:
    record = DetectionState()
    record = observe(record, 0.0, probability=0.9)
    record = observe(record, 1020.0, probability=0.9)
    record = observe(record, 4000.0, left=None, right=None, probability=None)
    assert record.detection is not None
    assert record.detection.minute.valid_samples == 2
    assert record.detection.minute.drowsy_samples == 2
    assert record.detection.minute.unavailable_samples == 58
    assert not record.detection.face_detected
    record = observe(record, 62000.0)
    assert record.detection is not None
    assert record.detection.minute.valid_samples == 1
    assert record.detection.minute.drowsy_samples == 0
    assert record.detection.minute.unavailable_samples == 59


def test_latest_picture_per_second_counts_and_history_stays_bounded() -> None:
    record = DetectionState()
    record = observe(record, 0.0, probability=0.9)
    record = observe(record, 900.0)
    assert record.detection is not None
    assert record.detection.minute.valid_samples == 1
    assert record.detection.minute.drowsy_samples == 0
    for index in range(1, 601):
        record = observe(record, float(index * 1000))
    assert len(record.samples) == 60
    assert record.detection is not None
    assert record.detection.minute.valid_samples == 60
    assert record.detection.minute.unavailable_samples == 0
    assert record.detection.frame_id == 602


def test_no_face_does_not_count_as_awake_and_alert_expires_with_history() -> None:
    record = DetectionState()
    for index in range(30):
        record = observe(record, float(index * 1000), probability=0.9)
    record = observe(record, 59000.0, left=None, right=None, probability=None)
    assert record.detection is not None
    assert record.detection.alert and not record.detection.face_detected
    assert record.detection.minute.valid_samples == 30
    record = observe(record, 90000.0, left=None, right=None, probability=None)
    assert record.detection is not None and not record.detection.alert
    assert record.detection.minute.valid_samples == 0
    assert record.detection.minute.unavailable_samples == 60


def test_eye_and_cnn_signals_combine_without_sharing_camera_history() -> None:
    first_camera = DetectionState()
    second_camera = DetectionState()
    for index in range(30):
        first_camera = observe(first_camera, float(index * 1000), left=0.1, right=0.1)
        second_camera = observe(second_camera, float(index * 1000), left=0.1, right=0.3)
    assert first_camera.detection is not None and first_camera.detection.alert
    assert second_camera.detection is not None and not second_camera.detection.alert
    assert second_camera.detection.minute.drowsy_samples == 0
    second_camera = observe(
        second_camera, 30000.0, left=None, right=None, probability=0.65
    )
    assert second_camera.detection is not None and second_camera.detection.face_detected
    assert second_camera.detection.minute.drowsy_samples == 1
    fresh = DetectionState()
    assert fresh.samples == () and fresh.detection is None


@pytest.mark.parametrize(
    ("left", "right", "probability", "valid_samples", "drowsy_samples"),
    [
        (0.20, 0.20, None, 1, 1),
        (0.20, 0.21, None, 1, 0),
        (0.21, 0.21, None, 1, 0),
        (None, None, 0.649, 1, 0),
        (None, None, 0.65, 1, 1),
        (0.10, None, None, 0, 0),
        (None, 0.10, None, 0, 0),
        (0.10, None, 0.65, 1, 1),
    ],
)
def test_frame_classification_preserves_signal_boundaries(
    left: float | None,
    right: float | None,
    probability: float | None,
    valid_samples: int,
    drowsy_samples: int,
) -> None:
    record = DetectionState()
    updated_record = observe(record, 0, left=left, right=right, probability=probability)
    detection = updated_record.detection
    assert detection is not None
    assert detection.minute.valid_samples == valid_samples
    assert detection.minute.drowsy_samples == drowsy_samples
    assert not detection.alert
