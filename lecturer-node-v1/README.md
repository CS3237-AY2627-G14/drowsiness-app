# Lecturer node firmware

Install the ESP32 Arduino board package, ESP32MQTTClient, ArduinoJson v6 and
LiquidCrystal I2C. Copy `LecturerNodeV1/config.example.h` to `config.h` in that
folder and set Wi-Fi and MQTT URI. Keep private config out of Git.

Open `LecturerNodeV1/LecturerNodeV1.ino`. The sketch follows main's `DisplayData`
handoff: the MQTT callback validates and queues a snapshot; `loop()` copies it
under `dataMux`, then updates the LCD and alarm outside the critical section.

## MQTT and display

The API publishes retained snapshots on `lect/result`:

```json
{"drowsy_seats":["1","3"]}
```

IDs must be nonempty strings containing ASCII letters and digits. The count comes from the array. The 16x2 LCD
shows `Drowsy: <count>` and the comma-separated IDs. Lists longer than 16 characters
scroll every 500 ms; shorter replacements overwrite the old line with padding.
An empty list shows `Drowsy: 0` and `No IDs reported`.

The JSON document has a 4096-byte capacity and the formatted ID buffer holds
1279 characters plus its terminator, including comma/space separators. Invalid
messages and snapshots that exceed either buffer are rejected completely and
leave the previous accepted state intact. Configure larger deployments with
these firmware limits in mind; snapshots are never silently truncated.

## Alarm behavior

The first valid snapshot after each connection establishes a silent baseline.
Invalid messages do not establish it. Subsequent additions trigger main's six
150 ms LED/buzzer phases. New additions during an alarm restart those phases.
Duplicates, reordering, removals and clears do not start or restart the alarm;
an already active alarm finishes normally. Duplicate snapshots also preserve
scroll progress. Added-seat requests remain pending until `loop()` consumes them,
even if later snapshots arrive first; the display uses the latest snapshot.

Scrolling and alarm phases use `millis()`. The loop retains main's 1 ms yield;
there are no blocking alarm delays. Hardware operations stay in `loop()`.

## Verification

With the ESP32 toolchain installed, compile from this project directory:

```sh
arduino-cli compile --fqbn esp32:esp32:esp32doit-devkit-v1 LecturerNodeV1
```

On hardware, send an empty retained baseline, then `["1"]`, `["1","3"]`, `["3","1"]`,
`["1"]`, and `[]`. Verify that only additions sound an alarm. Reconnect with a
nonempty retained list and verify a silent display refresh. Check IDs `1` and
`11`, long scrolling lists, shorter replacements, additions during an alarm,
and malformed, invalid-ID and oversized messages. Invalid input must not change
the LCD or establish the reconnect baseline.

Host checks cover the display and alarm logic with hardware stand-ins. They do
not establish successful ESP32 compilation, MQTT parsing/delivery, or physical
LCD, LED and buzzer behavior. Reflash together with the API update.

Reflash this firmware before restarting an API that publishes string seat IDs.
