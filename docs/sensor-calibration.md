# Sensor calibration and model operations

This prototype learns a **possible-drowsy sensor gate** for `student1` / seat 1.
The ESP32 continually sends measurements; the API learns and runs the sensor
classifier. Camera inference and the existing rolling alert remain in place.
Recordings, corrected labels, and previous models survive API restarts.

Initial labels represent acted postures. Good results on these recordings do not
establish accuracy for actual physiological drowsiness.

## 1. Configure and upload the student firmware

Open `student-node-v1/StudentNode/StudentNode.ino` in Arduino IDE. Install the
ESP32 board package, select **DOIT ESP32 DEVKIT V1**, and install
**ESP32MQTTClient** and **Adafruit VL53L0X** with their dependencies.

Copy `config.example.h` to `config.h` in the same sketch folder. Fill in Wi-Fi
credentials and the MQTT URI of the API computer, for example
`mqtt://192.168.1.100:1883`. Keep `NODE_ID` as `student1`. The private `config.h`
is ignored by Git. Upload normally and open Serial Monitor at 115200 baud.
Hardware wiring is assumed complete and correct.

The node publishes one packet every 200 ms to `drowsy/student1/raw`:

```json
{"schema_version":1,"boot_id":"unique-per-boot","sequence":123,"uptime_ms":24600,"upper_cm":8,"lower_mm":180,"back_adc":2450,"desk_adc":1700}
```

Distances are centimetres and millimetres respectively; pressures are raw
12-bit ADC readings (0–4095). Failed distance readings are `null`. Raw telemetry
uses QoS 0 and is not retained. Boot identity and sequence handle duplicate and
out-of-order messages. Device uptime is not an epoch timestamp.

Legacy `drowsy/student1/data` output remains available. `drowsy:-1` means unknown;
the API clears the previous classification instead of discarding that update.

## 2. Install and initialize

Use the platform setup in the root README; Windows development is documented
through WSL2. From `api/`, copy `.env.example` to `.env` if absent, then run:

```text
uv sync --locked
uv run python -m modules.processing.calibration init
docker compose up -d
uv run uvicorn main:app --host 0.0.0.0 --port 8000
```

From `webui/`, in another terminal:

```text
npm ci
npm run dev
```

Open **http://localhost:3000/calibration**. Verify live plots update, telemetry
age stays low, and the seat is occupied. Recording does not require a camera
stream. The optional camera rehearsal does.

Configuration in `api/.env`:

```text
DROWSINESS_CALIBRATION_DIRECTORY=.local/calibration
DROWSINESS_SENSOR_PRESENCE_MM=300
DROWSINESS_MQTT_SENSOR_MAX_AGE_SECONDS=5
```

The data directory is relative to `api/`. Initialization creates SQLite schema
explicitly; application startup never creates or migrates it. Without initialized
storage, legacy monitoring and live telemetry work but calibration controls are
unavailable. Restart after initialization or changing settings. A selected model
must match its saved feature, occupancy, and dependency configuration.

## 3. Record and label

1. Enter a participant alias and notes. Choose **Development** or **Reserved final
   test**. Click **Start recording**.
2. Settle into a posture before clicking **Begin label interval**. Select Awake,
   Drowsy posture, or Uncertain and describe the posture.
3. Hold a stable posture for 20–30 seconds, then click **Finish label interval**.
   Leave transitions unlabelled. Starting a recording alone assigns no labels.
4. Repeat awake and staged-drowsy episodes; finish with **Stop recording**.
5. Select a saved recording to correct interval times, labels, or posture notes.
   Times in the editor are seconds from recording start. Remove an interval or
   mark it Uncertain to exclude it. Click **Save labels**.

Overlapping intervals and intervals outside a recording are rejected. All label
revisions are retained. Existing model versions never change when labels change.
CSV exports contain raw values, server receipt timestamps, and the latest labels.

Start with four independent recordings across at least two sittings: three for
development and one reserved for final testing. Every development recording must
contain both classes with enough valid stable windows. Thousands of neighbouring
samples from one sitting are not independent test sessions.

Cover upright sitting, writing, reading with the head down, leaning back,
reaching, heavy desk pressure while awake, slumping, and resting the head on the
desk. Include awake and drowsy examples with similar values. Preserve the honest
labels; the model's permissive threshold handles ambiguity.

## 4. Train and interpret results

Select at least three completed development recordings and click **Train
candidate from selected recordings**. Training runs in the background and does
not change the active model. A failed job displays its error; recordings remain
available for correction and retry.

The API compares a decision tree and random forest with the old truth table and
an always-possible-drowsy baseline. It uses trailing two-second windows, including
sensor medians, variation, changes, and valid-reading fractions. Predictions
update once per second. Windows need at least eight packets; invalid lower
distance/pressure evidence, packet gaps, and label transitions are excluded.
Missing ultrasonic features use medians fitted only on each training fold.

Validation leaves one entire development recording out at a time. Threshold
selection targets at least 95% drowsy-posture recall and then minimizes awake
false positives. This target is not a guarantee for future observations.

Review:

- **Recall:** proportion of labelled drowsy windows passed onward to the camera.
- **Awake false-positive rate:** proportion of awake windows also passed onward.
- **TP / FN / FP / TN:** counts supporting those rates.
- **Coverage:** eligible labelled windows with usable occupied sensor evidence.
- **Weak separation:** awake and drowsy postures are difficult to distinguish;
  compare against the always-positive baseline before activation.
- **Reserved results and posture breakdown:** evaluated after model selection,
  without fitting or tuning against those recordings.

Only include the reserved recording when ready for final evaluation. Do not keep
tuning against its results; introduce a fresh reserved session after repeated
iteration. Model scores are not calibrated confidence percentages.

## 5. Rehearse with the camera

After candidate training, open `/streaming` in another tab and publish seat 1's
camera using its demo token. Return to `/calibration` and record a new rehearsal
with labelled awake and drowsy episodes, including head-down and awake face-loss
examples. The most recently trained candidate is scored alongside active and
legacy gates. Only the active gate can trigger the hardware alert.

Select the rehearsal recording to view **Camera rehearsal comparison**. It
replays the recorded camera measurements with each gate, reporting false alert
activations per labelled awake minute and alert latency for each drowsy episode.
No images are saved. A missing latency means no new alert started in that episode;
an alert already active on entering the episode is not counted as a new onset.
This diagnostic uses server receipt seconds rather than unsynchronized device or
browser clocks. A rehearsal with no published camera has no camera observations.

Keep one candidate and active model throughout a rehearsal. Train another
candidate after an API restart if you need to resume candidate comparison; the
active selection and saved reports persist independently.

## 6. Activate, monitor, improve, or roll back

Click **Activate this version** after reviewing its results. Loading and
validation must succeed before selection changes. Activation clears sensor
windows and rolling detection history, so allow new observations to accumulate.
Existing camera connections and seat ownership remain intact.

Before first activation, the corrected legacy truth table is the baseline.
After activation, raw telemetry owns seat 1's sensor classification: legacy
packets cannot overwrite it. Missing or stale raw telemetry produces unknown
evidence rather than silently falling back. Sensor evidence is attached when
the camera frame arrives, not after inference completes.

A sample counts as drowsy only when occupied and the sensor gate passes, plus
either CNN fatigue probability ≥0.65, both EARs <0.21, or no usable face in a
successfully processed frame. Sensor-awake suppresses the sample; unknown
evidence and unoccupied seats do not count. Camera disconnects do not create
no-face samples. An alert requires ≥10 valid seconds and ≥50% drowsy in the
rolling minute. Its off-to-on transition publishes `{"id":"A1"}` to
`drowsy/result`, QoS 1, for the existing LED/buzzer behavior.

For a correction, record the failing posture, adjust labels where necessary,
select old plus new development recordings, and train again. Dataset snapshots
and model artifacts remain immutable. No full recollection or firmware reflash
is required. Activate a previous completed version to roll back, or click
**Restore legacy baseline**. An interrupted recording is closed at next startup;
an interrupted training job is marked failed and can be retried.

## API reference

All paths are under `/api/calibration`; interactive schemas are at `/docs`.

| Method/path | Purpose |
| --- | --- |
| `GET /live`, `GET /events` | Current state / live server event stream |
| `GET /recordings`, `POST /recordings` | List / start with participant, notes, role |
| `GET /recordings/{id}` | Samples, labels, and camera measurements |
| `POST /recordings/{id}/stop` | Finish recording |
| `PUT /recordings/{id}/labels` | Replace current intervals, retaining revision history |
| `GET /recordings/{id}/export` | CSV with current labels |
| `GET /recordings/{id}/rehearsal` | Counterfactual fused alert comparison |
| `POST /training` | Start job with `{"recording_ids":["id1","id2","id3"]}` |
| `GET /models` | Jobs, errors, and completed reports |
| `POST /selection` | Activate/roll back with `{"model_id":"id"}`; null restores legacy |

Label intervals use epoch seconds from server receipt time, for example
`{"start":1800000000,"end":1800000030,"label":"awake","posture":"writing"}`.
Validation errors return 422; invalid operations return 409; uninitialized
calibration storage returns 503. These prototype controls have no user-account
authentication and are intended for the existing local development deployment.

## Backup and troubleshooting

Stop the API before copying the **entire** calibration directory, including the
SQLite database and model files. CSV export alone cannot restore labels' revision
history or model selection. Restore into the configured data directory using the
same locked dependencies. Load only locally generated model artifacts.

If an incompatible/missing selected artifact prevents startup, stop the API and
run this from `api/` to explicitly return to the legacy baseline, then restart:

```text
uv run python -m modules.processing.calibration reset-selection
```

This clears only model selection; recordings, labels, and previous artifacts stay
available for retraining or later rollback.

| Symptom | Check |
| --- | --- |
| No telemetry | Firmware Wi-Fi/broker URI, broker reachability, exact `student1` topic, schema, MQTT enabled |
| Controls unavailable | Run initialization from `api/`, then restart; check directory configuration |
| Unknown sensor result | Missing lower measurement, missing echo in baseline mode, insufficient window, unoccupied seat, or stale packets |
| Training fails | Three development recordings, both classes in each, stopped recordings, valid labelled windows |
| Too many face-loss alerts | Add awake head-down/look-away examples and review sensor false positives; no-face is an intentional confirmation rule |
| Camera rehearsal empty | Publish seat 1's camera during the recording; sensor-only recordings remain trainable |
| Selected model fails on startup | Restore its artifact/dependencies/configuration from backup; retrain after dependency changes |

Run the checks documented in the project READMEs. Software tests do not replace
the physical end-to-end rehearsal. See the dated [system changelog](../changelogs/2026-11-02-sensor-calibration/system.md)
for implementation and verification notes.
