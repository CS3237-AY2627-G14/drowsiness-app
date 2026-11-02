from modules.processing.schemas import SensorMeasurements

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
#  2  | Low    | Detected     | Low      | Lower   | no result
#  3  | Medium | Detected     | Low      | Lower   | no result
#  4  | High   | Detected     | Low      | Lower   | no result
#  5  | Low    | Detected     | Medium   | Lower   | no result
#  6  | Medium | Detected     | Medium   | Lower   | no result
#  7  | High   | Detected     | Medium   | Lower   | no result
#  8  | Low    | Detected     | High     | Lower   | no result
#  9  | Medium | Detected     | High     | Lower   | no result
#  10 | High   | Detected     | High     | Lower   | no result
#  11 | Low    | Detected     | Low      | Close   | drowsy
#  12 | Medium | Detected     | Low      | Close   | drowsy
#  13 | High   | Detected     | Low      | Close   | drowsy
#  14 | Low    | Detected     | Medium   | Close   | not drowsy
#  15 | Medium | Detected     | Medium   | Close   | drowsy
#  16 | High   | Detected     | Medium   | Close   | drowsy
#  17 | Low    | Detected     | High     | Close   | not drowsy
#  18 | Medium | Detected     | High     | Close   | drowsy
#  19 | High   | Detected     | High     | Close   | drowsy
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


def classify_sensor_measurements(
    measurements: SensorMeasurements,
) -> tuple[bool, bool | None]:
    present = 0 <= measurements.lower_mm < TOF_DETECT_MM
    if not present:
        return False, None
    # no echo (-1) = Low
    upper_level = classify_three_levels(
        measurements.upper_cm, US_LOW_MAX_CM, US_MED_MAX_CM
    )
    back_level = classify_three_levels(
        measurements.back_raw, BACK_LOW_MAX, BACK_MED_MAX
    )
    if measurements.desk_raw < DESK_BASE - DESK_TOLERANCE:
        desk_level = 0
    elif measurements.desk_raw > DESK_BASE + DESK_TOLERANCE:
        desk_level = 2
    else:
        desk_level = 1
    # Which row of the table the current readings match (1-28)
    # Rows 2-28 go: desk (Lower, Close, Higher) -> backrest (Low, Medium, High)
    # -> upper (Low, Medium, High)
    row = 2 + desk_level * 9 + back_level * 3 + upper_level
    return True, ROW_RESULT[row]


def classify_three_levels(value: int, low_max: int, medium_max: int) -> int:
    if value <= low_max:
        return 0
    if value <= medium_max:
        return 1
    return 2
