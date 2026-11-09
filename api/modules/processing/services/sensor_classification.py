import logging

from modules.processing.schemas import RawTelemetry, SensorMeasurements

logger = logging.getLogger(__name__)

# ---------- Placeholder thresholds: tune with sensor_test_4 ----------
# upper distance below 6 cm (0-5)  -> Low (head near the chair top)
US_LOW_MAX_CM = 5
# upper distance 6-9 cm            -> Medium, 10 cm and up -> High
US_MED_MAX_CM = 9
# lower distance < 300 mm  -> Detected (someone in the seat)
TOF_DETECT_MM = 300
# backrest FSR = 0         -> Low (not leaning)
BACK_LOW_MAX = 0
# backrest FSR 1-3000      -> Medium, above 3000 -> High
BACK_MED_MAX = 3000
# desk FSR base value
DESK_BASE = 1500
# 1000-2000 -> Close (light press), below 1000 -> Lower (not pressed),
# above 2000 -> Higher (heavy press)
DESK_TOLERANCE = 500

# ================= Truth table =================
#
#  #  | upper  | lower        | backrest | desk    | result
# ----+--------+--------------+----------+---------+-----------
#  1  | any    | Out-Of-Range | any      | any     | no result
#  2  | Low    | Detected     | Low      | 1000 - 2000   | no result
#  3  | Medium | Detected     | Low      | 1000 - 2000   | no result
#  4  | High   | Detected     | Low      | 1000 - 2000   | no result
#  5  | Low    | Detected     | Medium   | 1000 - 2000   | no result
#  6  | Medium | Detected     | Medium   | 1000 - 2000   | no result
#  7  | High   | Detected     | Medium   | 1000 - 2000   | no result
#  8  | Low    | Detected     | High     | 1000 - 2000   | no result
#  9  | Medium | Detected     | High     | 1000 - 2000   | no result
#  10 | High   | Detected     | High     | 1000 - 2000   | no result
#  11 | Low    | Detected     | Low      | Low   | drowsy
#  12 | Medium | Detected     | Low      | Low   | drowsy
#  13 | High   | Detected     | Low      | Low   | drowsy
#  14 | Low    | Detected     | Medium   | Low   | not drowsy
#  15 | Medium | Detected     | Medium   | Low   | drowsy
#  16 | High   | Detected     | Medium   | Low   | drowsy
#  17 | Low    | Detected     | High     | Low   | not drowsy
#  18 | Medium | Detected     | High     | Low   | drowsy
#  19 | High   | Detected     | High     | Low   | drowsy
#  20 | Low    | Detected     | Low      | Higher  | not drowsy
#  21 | Medium | Detected     | Low      | Higher  | drowsy
#  22 | High   | Detected     | Low      | Higher  | drowsy
#  23 | Low    | Detected     | Medium   | Higher  | not drowsy
#  24 | Medium | Detected     | Medium   | Higher  | drowsy
#  25 | High   | Detected     | Medium   | Higher  | drowsy
#  26 | Low    | Detected     | High     | Higher  | not drowsy
#  27 | Medium | Detected     | High     | Higher  | drowsy
#  28 | High   | Detected     | High     | Higher  | drowsy
#
# Change a result here if the team changes the table.
ROW_RESULT: tuple[bool | None, ...] = (
    None,  # (index 0 unused)
    None,  # 1
    None,  # 2
    None,  # 3
    None,  # 4
    None,  # 5
    None,  # 6
    None,  # 7
    None,  # 8
    None,  # 9
    None,  # 10
    True,  # 11
    True,  # 12
    True,  # 13
    False,  # 14
    True,  # 15
    True,  # 16
    False,  # 17
    True,  # 18
    True,  # 19
    False,  # 20
    True,  # 21
    True,  # 22
    False,  # 23
    True,  # 24
    True,  # 25
    False,  # 26
    True,  # 27
    True,  # 28
)


def classify_raw_telemetry(
    telemetry: RawTelemetry, captured_at_ms: float, presence_mm: int = 300
) -> SensorMeasurements:
    present = None if telemetry.lower_mm is None else telemetry.lower_mm < presence_mm
    drowsy = None
    table_index: int | None = None
    upper: int | None = None
    back: int | None = None
    desk: int | None = None
    # if present and telemetry.upper_cm is not None:
    if present:
        if  telemetry.upper_cm is None:
            upper = 0
        else:
            upper = classify_three_levels(telemetry.upper_cm, US_LOW_MAX_CM, US_MED_MAX_CM)
        back = classify_three_levels(telemetry.back_adc, BACK_LOW_MAX, BACK_MED_MAX)
        desk = 1 if telemetry.desk_adc < 1000 else 2 if telemetry.desk_adc > 2000 else 0
        table_index = 2 + desk * 9 + back * 3 + upper
        drowsy = ROW_RESULT[table_index]
    if drowsy is None:
        reason = (
            "lower distance missing"
            if telemetry.lower_mm is None
            else "seat unoccupied"
            if not present
            else "upper distance missing"
            if telemetry.upper_cm is None
            else f"truth table row {table_index} has no result"
        )
        logger.info(
            "Sensor gate unavailable: reason=%s boot_id=%s sequence=%d "
            "upper_cm=%s lower_mm=%s back_adc=%d desk_adc=%d "
            "levels(upper=%s, back=%s, desk=%s)",
            reason,
            telemetry.boot_id,
            telemetry.sequence,
            telemetry.upper_cm,
            telemetry.lower_mm,
            telemetry.back_adc,
            telemetry.desk_adc,
            upper,
            back,
            desk,
        )
    else:
        logger.debug(
            "Sensor gate classified: drowsy=%s boot_id=%s sequence=%d "
            "upper_cm=%d lower_mm=%d back_adc=%d desk_adc=%d "
            "levels(upper=%d, back=%d, desk=%d) truth_table_row=%d",
            drowsy,
            telemetry.boot_id,
            telemetry.sequence,
            telemetry.upper_cm,
            telemetry.lower_mm,
            telemetry.back_adc,
            telemetry.desk_adc,
            upper,
            back,
            desk,
            table_index,
        )
    return SensorMeasurements(
        drowsy=drowsy,
        present=present,
        captured_at_ms=captured_at_ms,
        unavailable_reason=None if drowsy is not None else "sensor_no_result",
    )


def classify_three_levels(value: int, low_max: int, medium_max: int) -> int:
    return 0 if value <= low_max else 1 if value <= medium_max else 2
