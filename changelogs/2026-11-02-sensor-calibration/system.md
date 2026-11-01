# System changes — 2026-11-02

## Sensor calibration and repeatable learning

- Added permanent ESP32 raw telemetry, backend feature extraction and learning,
  and `/calibration` in the existing web client for student1 / seat 1.
- Added recording, stable-interval labels, corrections/exclusion, CSV export,
  grouped validation, candidate reports, explicit activation, and rollback.
- Persist recordings, label revisions, immutable training snapshots, jobs, reports,
  artifacts, and active selection. Future calibration reuses existing data.
- Added live plots, occupancy/freshness, active/candidate scores, and camera
  rehearsal comparisons. Rehearsals save measurements without camera images;
  candidate predictions cannot trigger hardware alerts.
- Preserve the sensor gate AND (CNN ≥0.65 OR both EARs <0.21 OR no usable face)
  rule for occupied seats and successfully processed frames. Keep the rolling
  minute, 10-valid-sample minimum, 50% threshold, and `A1` MQTT alert activation.
- Snapshot sensor evidence at camera-frame admission. Model changes clear
  observations and reject previous-generation results without releasing seats.
- Correct legacy unknown handling and ultrasonic no-echo interpretation.
- Added the [operator guide](../../docs/sensor-calibration.md), updated project
  READMEs, and split [firmware](firmware.md) / [backend](backend.md) changelogs.

## Compatibility and limits

Only student1 / seat 1 has learned sensor classification. Existing legacy topics
remain available; after activation, raw telemetry is authoritative for that node.
Unknown evidence never silently becomes an awake/drowsy decision. Calibration
storage requires explicit initialization; existing monitoring can start without it.

Labels describe staged postures rather than validated physiological drowsiness.
The permissive sensor threshold requires evaluation of awake face-loss episodes.
Model selection is deliberate; there is no automatic learning from live predictions.
Keep a single API process and the locked dependencies used for saved artifacts.

## Verification

- Backend Ruff, formatting, and mypy pass. Full pytest: **135 passed, 2 skipped**
  (CUDA/MPS hardware unavailable); real CPU inference is included.
- Frontend typecheck, ESLint, Prettier, production build, and all **22 unit tests**
  pass. Both new Chrome calibration browser tests pass, covering recording,
  relabelling, training, activation/rollback, mobile width, and storage setup.
- k6 script unit tests: **4 passed**.
- React Doctor completed with no errors and three warnings: calibration-page
  complexity, similar table structures, and the existing serial frame loop.
- The full browser suite was attempted. After retrying with the API ready,
  **11 older streaming cases still fail** around camera lifecycle and older
  status assertions. Two representative camera failures reproduce against an
  isolated copy of the original HEAD web client. These failures are not claimed
  as fixed by sensor calibration. The new calibration tests use controlled API
  responses; backend integration tests separately exercise real SQLite and training.
- Arduino CLI is unavailable: firmware compilation/upload and physical MQTT,
  sensor timing, and LED/buzzer delivery were **not verified**.

The browser timing test now explicitly requests 10 FPS rather than assuming the
production default of 1 FPS. The oversized-frame backend test has a short parameter
ID, avoiding Windows' environment-variable length limit without changing coverage.

Native Windows MQTT was observed to require an event loop supporting `add_reader`;
the existing documented WSL/Linux workflow remains the supported setup. Streaming
browser checks can run with MQTT disabled; those checks do not establish physical
MQTT delivery.
