# Student node firmware

Arduino C++ for the ESP32 student sensor node. The sketch is now
[`StudentNode/StudentNode.ino`](StudentNode/StudentNode.ino); the previous
`log_sensors.ino.py` filename incorrectly suggested Python.

## Setup and upload

Hardware is assumed complete. In Arduino IDE, install Espressif's ESP32 board
package, select **DOIT ESP32 DEVKIT V1**, and select the connected serial port.
Install **ESP32MQTTClient** and **Adafruit VL53L0X** and their dependencies.

Copy `StudentNode/config.example.h` to `StudentNode/config.h`. Set Wi-Fi and the
broker URI, retaining `NODE_ID "student1"`. `config.h` is ignored by Git.
Open the sketch folder, compile, upload, and open Serial Monitor at 115200 baud.

With Arduino CLI and the board/libraries already installed, from this directory:

```text
arduino-cli compile --fqbn esp32:esp32:esp32doit-devkit-v1 StudentNode
arduino-cli upload --fqbn esp32:esp32:esp32doit-devkit-v1 --port COM5 StudentNode
```

Replace `COM5` with your board's port (for example `/dev/ttyUSB0` on Linux).
Dependencies and board tooling belong to this firmware project; it does not
import backend or web client source.

## Behavior

- Publish raw upper distance (cm), lower distance (mm), and both FSR ADC readings
  every 200 ms on `drowsy/student1/raw`, QoS 0, non-retained.
- Include schema version, unique boot ID, sequence, and extended device uptime.
  Invalid distance measurements are JSON null.
- Keep the original truth table's periodic/change-driven legacy results on
  `drowsy/student1/data`. Unknown is -1; no echo is never a near-head measurement.
- Listen on `drowsy/result` for `{"id":"A1"}`. Blink/beep for five seconds,
  restarting that period if another matching notification arrives.

Use the [calibration guide](../docs/sensor-calibration.md) for the complete
record → label → train → rehearse → activate workflow. Learning runs on the API;
normal recalibration does not require another firmware upload.

## Verification

Compile with the installed ESP32 toolchain, inspect raw packets while changing
posture, verify null distance packets and reboot sequence handling, then rehearse
camera fusion and LED/buzzer delivery. Host tests cover packet parsing and model
logic; they do not verify sensors, timing on the physical board, or outputs.

See the [firmware changelog](../changelogs/2026-11-02-sensor-calibration/firmware.md).
