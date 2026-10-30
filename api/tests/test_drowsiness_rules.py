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
    sensor_drowsy: bool | None = True,
    present: bool | None = True,
) -> DetectionState:
    measurements = FrameMeasurements(
        connection_id=uuid4(),
        frame_id=record.detection.frame_id + 1 if record.detection is not None else 1,
        captured_at_ms=captured_at_ms,
        left_ear=left,
        right_ear=right,
        fatigue_probability=probability,
        sensor_drowsy=sensor_drowsy,
        present=present,
    )
    settings = Settings()
    return evaluate_measurements(record, measurements, settings)


def test_minute_alert_requires_10_valid_samples_and_at_least_half_drowsy() -> None:
    record = DetectionState()
    for index in range(10):
        probability = 0.9 if index < 5 else 0.1
        record = observe(
            record, float(index * 1400 + (index % 3) * 20), probability=probability
        )
        assert record.detection is not None
        if index < 9:
            assert not record.detection.alert
    assert record.detection is not None
    assert record.detection.minute.valid_samples == 10
    assert record.detection.minute.drowsy_samples == 5
    assert record.detection.minute.unavailable_samples == 50
    assert record.detection.alert
    record = observe(record, 43000.0)
    assert record.detection is not None and not record.detection.alert


def test_missing_observations_are_unknown_and_old_samples_expire() -> None:
    record = DetectionState()
    record = observe(record, 0.0, probability=0.9)
    record = observe(record, 1020.0, probability=0.9)
    record = observe(
        record,
        4000.0,
        left=None,
        right=None,
        probability=None,
        sensor_drowsy=None,
    )
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
    for index in range(10):
        record = observe(record, float(index * 1000), probability=0.9)
    record = observe(
        record, 11000.0, left=None, right=None, probability=None, sensor_drowsy=True
    )
    assert record.detection is not None
    assert record.detection.alert and not record.detection.face_detected
    assert record.detection.minute.valid_samples == 11
    record = observe(
        record,
        70000.0,
        left=None,
        right=None,
        probability=None,
        sensor_drowsy=None,
    )
    assert record.detection is not None and not record.detection.alert
    assert record.detection.minute.valid_samples == 1
    assert record.detection.minute.unavailable_samples == 59


def test_eye_and_cnn_signals_combine_without_sharing_camera_history() -> None:
    first_camera = DetectionState()
    second_camera = DetectionState()
    for index in range(10):
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
        (0.10, None, None, 1, 1),
        (None, 0.10, None, 1, 1),
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


def test_unoccupied_sensor_sample_is_unknown_and_exposes_sensor_result() -> None:
    measurement = FrameMeasurements(
        connection_id=uuid4(),
        frame_id=1,
        captured_at_ms=1000.0,
        left_ear=0.1,
        right_ear=0.1,
        fatigue_probability=0.9,
        sensor_drowsy=True,
        present=False,
    )

    result = evaluate_measurements(DetectionState(), measurement, Settings())

    assert result.detection is not None
    assert result.detection.minute.valid_samples == 0
    assert result.detection.minute.drowsy_samples == 0
    assert result.detection.sensor_drowsy is True
    assert result.detection.present is False


@pytest.mark.parametrize(
    ("sensor_drowsy", "camera_state", "expected_valid_samples", "expected_drowsy"),
    [
        (True, "drowsy", 1, 1),
        (True, "awake", 1, 0),
        (True, "no_face", 1, 1),
        (False, "drowsy", 1, 0),
        (False, "no_face", 1, 0),
        (None, "drowsy", 0, 0),
    ],
)
def test_sensor_and_camera_results_are_fused(
    sensor_drowsy: bool | None,
    camera_state: str,
    expected_valid_samples: int,
    expected_drowsy: int,
) -> None:
    left_ear, right_ear, probability = {
        "drowsy": (0.1, 0.1, 0.9),
        "awake": (0.3, 0.3, 0.1),
        "no_face": (None, None, None),
    }[camera_state]
    measurement = FrameMeasurements(
        connection_id=uuid4(),
        frame_id=1,
        captured_at_ms=1000.0,
        left_ear=left_ear,
        right_ear=right_ear,
        fatigue_probability=probability,
        sensor_drowsy=sensor_drowsy,
        present=True,
    )

    result = evaluate_measurements(DetectionState(), measurement, Settings())

    assert result.detection is not None
    assert result.detection.minute.valid_samples == expected_valid_samples
    assert result.detection.minute.drowsy_samples == expected_drowsy
