# Student node firmware

Open `StudentNode/StudentNode.ino` using the ESP32 Arduino board package and
DOIT ESP32 DEVKIT V1 board. Install ESP32MQTTClient, ArduinoJson v6, and Adafruit
VL53L0X. Copy `StudentNode/config.example.h` to `StudentNode/config.h`, configure
Wi-Fi, MQTT URI and the numeric seat ID string, then compile and upload.
The private configuration is ignored by Git. Wiring is documented in the sketch.

The node publishes versioned raw telemetry every 200 ms on
`drowsy/stud/<seat_id>/data`; failed distances are null. The API owns detection.
It receives `{"drowsy":true}` on `drowsy/stud/<seat_id>/result` and alerts for
five seconds on false-to-true transitions. Repeated true does not extend it;
false re-arms it. Reflash together with the API update.

Run `arduino-cli compile --fqbn esp32:esp32:esp32doit-devkit-v1 StudentNode`
from this project when the toolchain is installed. Check raw packets, reboot
ordering, invalid readings and LED/buzzer timing on hardware.

See the [calibration guide](../docs/sensor-calibration.md).
