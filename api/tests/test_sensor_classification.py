import pytest

from modules.processing.calibration.schemas import RawTelemetry
from modules.processing.services.sensor_classification import (
    classify_raw_telemetry,
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
    reading = RawTelemetry(
        schema_version=1,
        boot_id="test",
        sequence=1,
        uptime_ms=200,
        upper_cm=(3, 7, 12)[upper],
        lower_mm=150,
        back_adc=(0, 1500, 3500)[back],
        desk_adc=(500, 1500, 2500)[desk],
    )
    assert classify_raw_telemetry(reading, 0.0).drowsy == EXPECTED[index]


@pytest.mark.parametrize(
    ("upper", "lower", "back", "desk", "present", "drowsy"),
    [
        (7, -1, 1000, 1500, None, None),
        (7, 300, 1000, 1500, False, None),
        (7, 299, 1000, 1500, True, True),
        (-1, 150, 1000, 1500, True, None),
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
    present: bool | None,
    drowsy: bool | None,
) -> None:
    reading = RawTelemetry(
        schema_version=1,
        boot_id="test",
        sequence=1,
        uptime_ms=200,
        upper_cm=None if upper == -1 else upper,
        lower_mm=None if lower == -1 else lower,
        back_adc=back,
        desk_adc=desk,
    )
    result = classify_raw_telemetry(reading, 0.0)
    assert (result.present, result.drowsy) == (present, drowsy)
