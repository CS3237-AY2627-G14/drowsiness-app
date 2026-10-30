# Student node

ESP32 DOIT DEVKIT V1 firmware. Install ESP32MQTTClient, ArduinoJson (v6), and
Adafruit_VL53L0X through Arduino Library Manager. Copy config.example.h to
config.h and set Wi-Fi, the base broker address and numeric SEAT_ID. Keep config.h
out of Git. Open log_sensors.ino in Arduino IDE (use its matching sketch folder
when prompted, including config.h), select the board, compile and upload.

Wiring is documented in the sketch. Every 200 ms the node publishes four raw
readings to drowsy/stud/<seat_id>/data. The Python base owns all detection rules.
The node listens to drowsy/stud/<seat_id>/result and runs the five-second
LED/buzzer sequence on a false-to-true drowsy result. Repeated true results do
not extend the sequence; false re-arms it. Reflash together with the API update.
