from uuid import uuid4

import pytest

from core.config import Settings
from modules.processing.schemas import DetectionState, FrameMeasurements
from modules.processing.utils.drowsiness_rules import (
    evaluate_measurements,
    reclassify_latest_sample,
)


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


def test_historical_majority_cannot_trigger_on_an_awake_frame() -> None:
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
    assert not record.detection.alert
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


def test_no_face_is_unknown_and_alert_expires_with_history() -> None:
    record = DetectionState()
    for index in range(10):
        record = observe(record, float(index * 1000), probability=0.9)
    record = observe(
        record, 10000.0, left=None, right=None, probability=None, sensor_drowsy=True
    )
    assert record.detection is not None
    assert record.detection.alert and not record.detection.face_detected
    assert record.detection.minute.valid_samples == 10
    record = observe(
        record,
        69999.0,
        left=None,
        right=None,
        probability=None,
        sensor_drowsy=None,
    )
    assert record.detection is not None and not record.detection.alert
    assert record.detection.minute.valid_samples == 0
    assert record.detection.minute.unavailable_samples == 60


def test_sensor_reclassification_updates_alert_from_rolling_window() -> None:
    record = DetectionState()
    for index in range(10):
        record = observe(
            record,
            float(index * 1000),
            probability=0.9 if index < 4 or index == 9 else 0.1,
        )
    assert record.detection is not None and record.detection.alert

    latest = FrameMeasurements(
        connection_id=uuid4(),
        frame_id=record.detection.frame_id,
        captured_at_ms=record.detection.captured_at_ms,
        left_ear=0.3,
        right_ear=0.3,
        fatigue_probability=0.1,
        sensor_drowsy=True,
        present=True,
    )
    record = reclassify_latest_sample(record, latest, Settings())

    assert len(record.samples) == 10
    assert record.detection is not None
    assert record.detection.minute.valid_samples == 10
    assert record.detection.minute.drowsy_samples == 4
    assert not record.detection.alert


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
        (0.10, None, None, 1, 0),
        (None, 0.10, None, 1, 0),
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
        (True, "no_face", 0, 0),
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


@pytest.mark.parametrize("interval_ms", [100, 500, 1000])
def test_streak_uses_elapsed_time_not_frame_count(interval_ms: int) -> None:
    state = DetectionState()
    for timestamp in range(0, 5001, interval_ms):
        state = observe(state, float(timestamp), probability=0.9)
        assert state.detection is not None
        assert state.detection.alert is (timestamp >= 5000)
    assert state.detection is not None
    assert state.detection.minute.valid_samples == 6


@pytest.mark.parametrize("unknown", [False, True])
def test_interruption_within_second_cannot_be_overwritten(unknown: bool) -> None:
    state = DetectionState()
    for timestamp in range(0, 5001, 500):
        state = observe(state, float(timestamp), probability=0.9)
    state = observe(
        state, 5100.0, probability=0.1, sensor_drowsy=None if unknown else True
    )
    assert state.drowsy_since_ms is None
    assert state.detection is not None and state.detection.alert
    state = observe(state, 5200.0, probability=0.9)
    assert state.drowsy_since_ms == 5200.0
    assert state.detection is not None and state.detection.alert


def test_gap_breaks_streak_and_reset_state_discards_it() -> None:
    state = DetectionState()
    for timestamp in range(0, 5001, 1000):
        state = observe(state, float(timestamp), probability=0.9)
    assert state.detection is not None and state.detection.alert
    state = observe(state, 6001.0, probability=0.9)
    assert state.drowsy_since_ms == 6001.0
    assert state.detection is not None and state.detection.alert
    assert DetectionState().drowsy_since_ms is None


def test_sensor_reclassification_does_not_advance_or_restore_streak() -> None:
    from modules.processing.utils.drowsiness_rules import reclassify_latest_sample

    state = DetectionState()
    for timestamp in range(0, 5001, 1000):
        state = observe(state, float(timestamp), probability=0.9)
    measurements = FrameMeasurements(
        connection_id=uuid4(),
        frame_id=6,
        captured_at_ms=5000.0,
        left_ear=0.1,
        right_ear=0.1,
        present=True,
        sensor_drowsy=None,
    )
    state = reclassify_latest_sample(state, measurements, Settings())
    assert state.drowsy_since_ms is None
    assert state.detection is not None and state.detection.alert
    recovered = measurements.model_copy(update={"sensor_drowsy": True})
    for _ in range(20):
        state = reclassify_latest_sample(state, recovered, Settings())
        assert state.drowsy_since_ms == 5000.0
        assert state.detection is not None and state.detection.alert
    assert len(state.samples) == 6


def test_configured_streak_threshold_and_validation() -> None:
    from pydantic import ValidationError

    for invalid in (0, -1):
        with pytest.raises(ValidationError):
            Settings(drowsy_streak_seconds=invalid)
    state = DetectionState()
    settings = Settings(drowsy_streak_seconds=2)
    for timestamp in (0.0, 999.0, 1999.0, 2000.0):
        measurement = FrameMeasurements(
            connection_id=uuid4(),
            frame_id=1,
            captured_at_ms=timestamp,
            left_ear=0.1,
            right_ear=0.1,
            present=True,
            sensor_drowsy=True,
        )
        state = evaluate_measurements(state, measurement, settings)
        assert state.detection is not None
        assert state.detection.alert is (timestamp >= 2000)


def test_recovery_requires_continuous_awake_evidence() -> None:
    state = DetectionState()
    for timestamp in range(0, 5001, 1000):
        state = observe(state, float(timestamp), probability=0.9)
    for awake_at in (5100.0, 6100.0, 7100.0, 8099.0):
        state = observe(state, awake_at, probability=0.1)
        assert state.detection is not None and state.detection.alert
    state = observe(state, 8100.0, probability=0.1)
    assert state.detection is not None and not state.detection.alert


def test_unknown_timeout_does_not_restart_with_more_unknown_frames() -> None:
    state = DetectionState()
    for timestamp in range(0, 5001, 1000):
        state = observe(state, float(timestamp), probability=0.9)
    for unknown_at in (5100.0, 6100.0, 7100.0, 8100.0, 9100.0, 10099.0):
        state = observe(state, unknown_at, sensor_drowsy=None)
        assert state.detection is not None and state.detection.alert
        assert state.unknown_since_ms == 5100.0
    state = observe(state, 10100.0, sensor_drowsy=None)
    assert state.detection is None
    state = observe(state, 10150.0, sensor_drowsy=None)
    assert state.detection is None
    state = observe(state, 10200.0, probability=0.9)
    assert state.detection is not None and not state.detection.alert
    assert state.drowsy_since_ms == 10200.0


def test_drowsiness_cancels_recovery_and_absence_clears_immediately() -> None:
    state = DetectionState()
    for timestamp in range(0, 5001, 1000):
        state = observe(state, float(timestamp), probability=0.9)
    state = observe(state, 5100.0, probability=0.1)
    state = observe(state, 5200.0, probability=0.9)
    assert state.awake_since_ms is None
    state = observe(state, 5300.0, present=False)
    assert state.detection is not None and not state.detection.alert
    assert state.drowsy_since_ms is None and state.awake_since_ms is None
