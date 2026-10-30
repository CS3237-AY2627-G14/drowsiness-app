import pytest

from modules.processing.schemas import SensorMeasurements
from modules.processing.services.sensor_classification import (
    classify_sensor_measurements,
)

EXPECTED = [
    None,
    None,
    None,
    None,
    None,
    None,
    None,
    None,
    None,
    True,
    True,
    True,
    False,
    True,
    True,
    False,
    True,
    True,
    False,
    True,
    True,
    False,
    True,
    True,
    False,
    True,
    True,
]


@pytest.mark.parametrize("index", range(27))
def test_original_truth_table(index: int) -> None:
    desk, remainder = divmod(index, 9)
    back, upper = divmod(remainder, 3)
    reading = SensorMeasurements(
        upper_cm=(3, 7, 12)[upper],
        lower_mm=150,
        back_raw=(0, 1500, 3500)[back],
        desk_raw=(500, 1500, 2500)[desk],
        captured_at_ms=0.0,
    )
    assert classify_sensor_measurements(reading) == (True, EXPECTED[index])


@pytest.mark.parametrize(
    ("upper", "lower", "back", "desk", "present", "drowsy"),
    [
        (7, -1, 1000, 1500, False, None),
        (7, 300, 1000, 1500, False, None),
        (7, 299, 1000, 1500, True, True),
        (-1, 150, 1000, 1500, True, False),
        (5, 150, 1000, 1500, True, False),
        (6, 150, 1000, 1500, True, True),
        (9, 150, 1000, 1500, True, True),
        (10, 150, 1000, 1500, True, True),
        (3, 150, 0, 1500, True, True),
        (3, 150, 1, 1500, True, False),
        (3, 150, 3000, 1500, True, False),
        (3, 150, 3001, 1500, True, False),
        (3, 150, 0, 999, True, None),
        (3, 150, 0, 1000, True, True),
        (3, 150, 0, 2000, True, True),
        (3, 150, 0, 2001, True, False),
    ],
)
def test_sensor_boundaries(
    upper: int,
    lower: int,
    back: int,
    desk: int,
    present: bool,
    drowsy: bool | None,
) -> None:
    reading = SensorMeasurements(
        upper_cm=upper,
        lower_mm=lower,
        back_raw=back,
        desk_raw=desk,
        captured_at_ms=0.0,
    )
    assert classify_sensor_measurements(reading) == (present, drowsy)
