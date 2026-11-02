# Drowsiness API

FastAPI backend and inference project in the [monorepo](../README.md). The React
camera client lives in [../webui](../webui/README.md). Run the API natively; Docker
runs only the local MQTT broker.

## Setup

Requires Git, [uv](https://docs.astral.sh/uv/getting-started/installation/), Python
3.12, Node.js 22.x (22.12+), and Docker with Compose.

On Windows, run all commands inside **WSL2** (for example, Ubuntu). Install Git,
uv, Python and Node inside WSL and keep the checkout under your Linux home
directory, such as `~/projects/`. Enable your distro in Docker Desktop's
**Settings → Resources → WSL Integration** and use Linux containers
([Docker setup](https://docs.docker.com/desktop/features/wsl/)). Do not reuse
Windows `.venv` or `node_modules` directories.

From the repository root in WSL, Linux or macOS, with Docker running
(skip the copy if `api/.env` already exists):

```bash
cd api
cp .env.example .env
uv sync --locked
docker compose up -d
```

Start the API in that terminal (use `DROWSINESS_INFERENCE_DEVICE=cpu` in `.env`
for a CPU-only setup):

```text
uv run uvicorn main:app --host 0.0.0.0 --port 8000
```

In another terminal, starting from the repository root:

```text
cd webui
npm ci
npm run dev
```

Open http://localhost:3000/streaming. Select a seat, start the camera, then Publish.
Demo tokens look like `demo-room-101-seat-1`. Use Ctrl+C to stop the API and Vite;
`docker compose down` stops the broker. When using WSL, open the page in your
Windows browser to use its camera. WSL execution remains unverified.

## Sensor calibration

After `uv sync --locked`, initialize persistent calibration storage explicitly:

```text
uv run python -m modules.processing.calibration init
```

Restart the API and open http://localhost:3000/calibration. The backend adds
scikit-learn and joblib for recording-session validation, training, and artifacts.
Training runs in a background thread; activation is explicit and reversible.

`DROWSINESS_CALIBRATION_DIRECTORY` defaults to `.local/calibration` and
`DROWSINESS_SENSOR_PRESENCE_MM` to `300`. Startup never creates or migrates schema.
Without initialized storage, existing monitoring works but persistent calibration
operations return 503. SQLite recordings, label revisions, immutable dataset
snapshots, models, reports, and selection survive restarts. Stop the API before
backing up the complete directory. Rooms and authorization sessions remain
in memory.

The `/api/calibration` API provides recordings, labels, CSV export, live SSE
telemetry, background training, reports, selection/rollback, and camera rehearsal
reports. See `/docs` for schemas and the [operator guide](../docs/sensor-calibration.md)
for exact workflows. See the [backend changelog](../changelogs/2026-11-02-sensor-calibration/backend.md)
for implementation and verification details.

## Configuration

Copying [.env.example](.env.example) supplies the required session TTL, seat count
and publisher limit. Backend settings use `DROWSINESS_`; shell variables override
`api/.env`. The API loads `.env` and relative model paths from its working
directory, so always start it from `api/`. Optional
frontend overrides belong in `../webui/.env.local`. Restart after changing settings.

The [MobileNetV4 checkpoint](models/README.md) is included. Device `auto` prefers
CUDA, then Apple MPS, then CPU. MPS needs native macOS; CUDA needs compatible
NVIDIA hardware and a CUDA-enabled PyTorch installation. Keep one API process.

Camera access needs localhost or trusted HTTPS. For remote cameras, set both
`DEV_TLS_CERT` and `DEV_TLS_KEY` in `../webui/.env.local` and add the exact HTTPS
origin to `DROWSINESS_ALLOWED_ORIGINS`. Certificate paths resolve from `../webui`;
use Linux paths in WSL. Do not commit private keys or credentials.

## MQTT

Student nodes publish versioned telemetry every 200 ms to
`drowsy/stud/<seat_id>/data` (QoS 0, non-retained):

```json
{"schema_version":1,"boot_id":"unique-per-boot","sequence":123,"uptime_ms":24600,"upper_cm":8,"lower_mm":180,"back_adc":2450,"desk_adc":1700}
```

Distances are centimetres and millimetres; invalid distances are `null`.
ADC readings range from 0 to 4095. Boot identity, sequence and uptime reject old
packets. Reflash all student nodes with this API; older payloads are unsupported.

The API owns the corrected sensor truth table and learned seat 1 classifier.
Missing ultrasonic echo gives unknown baseline evidence. Fresh sensor evidence
(up to five seconds old) combines with camera measurements. Sensor-awake counts
as awake; sensor-drowsy counts when the camera agrees or has no face measurements.
An awake camera overrides a drowsy sensor. Missing evidence and unoccupied seats
do not count. New sensor readings can revise the latest combined sample without
adding observations. The rolling minute uses the latest picture per second and
requires ten valid samples with at least half drowsy.

Results publish at QoS 1 to `drowsy/stud/<seat_id>/result` as `{"drowsy":true}`.
Student nodes alert for five seconds on false-to-true transitions. Sensor-driven
publications occur at most once per second, except alert changes. The lecturer
receives retained `{"drowsy_seats":[1,3]}` on `drowsy/lect/result`; empty lists clear
its display. The old hardcoded A1 notification is removed. The UI publication
indicator is per-seat and confirms broker publication, not hardware execution.

Set `DROWSINESS_MQTT_ENABLED=false` to disable MQTT or configure
`DROWSINESS_MQTT_HOST` and `DROWSINESS_MQTT_PORT`. Connections retry broker failures
and refresh current status after reconnect. Camera uploads use Socket.IO.

See the [calibration guide](../docs/sensor-calibration.md) for recording, training, rehearsal,
activation and rollback. Calibration data persists locally; live history remains
in memory. Rehearsal is a one-second diagnostic, stores no images, and candidate
comparisons do not trigger hardware alerts.

## Checks

From `api/` (the working directory for all backend commands):

```text
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
```

From `../webui`:

```text
npm run typecheck
npm run lint
npm run check
npm run test
npm run build
npm run test:e2e
npx -y react-doctor@latest . --verbose --scope full
```

Browser tests need the API and Vite running, ten demo seats, and Google Chrome
in the environment running Playwright. For WSL, install Linux Chrome from
`../webui` with `npx playwright install --with-deps chrome`; tests use a synthetic
camera. Load-test scripts live in `scripts/k6`; run their unit tests with
`node --test scripts/k6/streaming.test.mjs` from `api/`.

See [architecture](docs/architecture.md) for module responsibilities and data flow.
