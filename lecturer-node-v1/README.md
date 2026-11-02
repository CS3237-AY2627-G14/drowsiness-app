# Lecturer node firmware

Install the ESP32 Arduino board package, ESP32MQTTClient, ArduinoJson v6 and
LiquidCrystal I2C. Copy `LecturerNodeV1/config.example.h` to `config.h` in that
folder and set Wi-Fi and MQTT URI. Keep private config out of Git.

The 16x2 LCD displays the retained `drowsy/lect/result` seat list. Empty lists
clear it; long lists page every two seconds. Newly added seats trigger the
existing notification pattern. The first snapshot after reconnect updates the
display without sounding an alert. Reflash with the API update.

Compile the `LecturerNodeV1` sketch and check display, paging, empty lists and
reconnect behavior on hardware. Wiring is documented in the sketch.
