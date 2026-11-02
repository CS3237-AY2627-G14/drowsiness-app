# Student firmware changes — 2026-11-02

- Moved Arduino C++ from `student-node-v1/log_sensors.ino.py` into
  `student-node-v1/StudentNode/StudentNode.ino`.
- Replaced checked-in Wi-Fi/broker values with ignored `config.h` and a committed
  `config.example.h`. Keep `NODE_ID` set to `student1` for this prototype.
- Added `drowsy/student1/raw` publishing every 200 ms, QoS 0, non-retained. Packets
  contain schema version 1, boot ID, sequence, extended uptime, upper distance in
  cm, lower distance in mm, and back/desk raw ADC values.
- Failed distance measurements become JSON null. Missing ultrasonic echoes no
  longer represent the low-distance category; legacy classification becomes -1.
- Preserve the truth table, periodic/change-driven legacy publication, and
  `drowsy/result` / `{"id":"A1"}` five-second LED/buzzer alert behavior.
- Corrected alert-topic comments and preserved immediate legacy updates when
  sensor validity changes.

## Setup and verification

Copy the example configuration to `config.h`, install the ESP32 board package and
ESP32MQTTClient / Adafruit VL53L0X libraries, then compile and upload the sketch.
Exact IDE/CLI steps are in the [firmware README](../../student-node-v1/README.md).

Arduino CLI is not installed in this workspace, so firmware compilation/upload
and physical timing, sensor readings, and LED/buzzer operation were not verified.
Backend contract tests validate the new packets, null readings, duplicate/out-of-order
rejection, boot transitions, and legacy unknown handling. See [system checks](system.md).
