"""Base-owned interpretation of the student node's four raw sensors."""

from modules.processing.schemas import SensorMeasurements

UPPER_LOW_MAX_CM = 5
UPPER_MEDIUM_MAX_CM = 9
PRESENCE_MAX_MM = 300
BACK_LOW_MAX = 0
BACK_MEDIUM_MAX = 3000
DESK_BASE = 1500
DESK_TOLERANCE = 500

# Index zero is unused; rows match the team's original firmware truth table.
ROW_RESULTS: tuple[bool | None, ...] = (
    None,
    None,
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
)


def classify_sensor_measurements(
    measurements: SensorMeasurements,
) -> tuple[bool, bool | None]:
    """Return presence and the nullable sensor drowsiness decision."""
    present = 0 <= measurements.lower_mm < PRESENCE_MAX_MM
    if not present:
        return False, None
    upper_level = classify_three_levels(
        measurements.upper_cm, UPPER_LOW_MAX_CM, UPPER_MEDIUM_MAX_CM
    )
    back_level = classify_three_levels(
        measurements.back_raw, BACK_LOW_MAX, BACK_MEDIUM_MAX
    )
    if measurements.desk_raw < DESK_BASE - DESK_TOLERANCE:
        desk_level = 0
    elif measurements.desk_raw > DESK_BASE + DESK_TOLERANCE:
        desk_level = 2
    else:
        desk_level = 1
    row = 2 + desk_level * 9 + back_level * 3 + upper_level
    return True, ROW_RESULTS[row]


def classify_three_levels(value: int, low_max: int, medium_max: int) -> int:
    if value <= low_max:
        return 0
    if value <= medium_max:
        return 1
    return 2
