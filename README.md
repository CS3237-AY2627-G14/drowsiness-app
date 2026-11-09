# Drowsiness detection monorepo

The API and camera client live in independent projects in one repository. Add
other project code as sibling directories, using the tooling suited to each one.

| Project | Purpose | Tooling | Documentation |
| --- | --- | --- | --- |
| [`api/`](api/) | FastAPI backend, inference, and local MQTT broker configuration | Python 3.12, uv, Docker Compose | [API guide](api/README.md) |
| [`student-node-v1/`](student-node-v1/) | Raw sensor acquisition and alert actuator | Arduino ESP32 | [Firmware guide](student-node-v1/README.md) |
| [`lecturer-node-v1/`](lecturer-node-v1/) | ESP32 lecturer seat-list display and alerts | Arduino ESP32 | [Firmware guide](lecturer-node-v1/README.md) |
| [`webui/`](webui/) | React camera client | Node.js 22.x (22.12+), npm, Vite | [Web client guide](webui/README.md) |

## Get started

Install Git, [uv](https://docs.astral.sh/uv/getting-started/installation/), Python
3.12, and Node.js 22.x (22.12+). Docker with Compose is needed for the local
MQTT broker. On Windows, use WSL2 and keep the checkout in its Linux filesystem;
see the [API guide](api/README.md) for Docker setup.

From the repository root:

```bash
cd api
cp .env.example .env  # Skip if .env already exists
uv sync --locked
docker compose up -d
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

In another terminal, from the repository root:

```bash
cd webui
cp .env.example .env  # Skip if .env already exists
npm ci
npm run dev
```

Open http://localhost:3000/streaming. Select a seat, start the camera, then Publish.
The API runs at http://localhost:8000; health is at `/health` and API docs at
`/docs`. Stop the app terminals with Ctrl+C and the broker with
`docker compose down` from `api/`.
MQTT carries sensor input and drowsiness alert notifications; camera uploads use
Socket.IO.

## Sensor calibration

The ESP32 sends raw measurements continuously. The backend learns a sensor gate
from labelled staged postures; camera inference confirms possible drowsiness.
Saved recordings and model versions support repeated calibration.

1. Configure/upload the [student sketch](student-node-v1/README.md).
2. From `api/`, run `uv run python -m modules.processing.calibration init`, then
   start the broker, API, and web client as above.
3. Open http://localhost:3000/calibration. Record and label at least three
   independent development sessions containing both awake and drowsy postures.
4. Train a candidate, review validation and a separate reserved session, rehearse
   with seat 1's camera, then explicitly activate it. Older models remain
   available for rollback; corrections reuse existing recordings.

See the complete [operator guide](docs/sensor-calibration.md) and dated
[system](changelogs/2026-11-02-sensor-calibration/system.md),
[firmware](changelogs/2026-11-02-sensor-calibration/firmware.md), and
[backend](changelogs/2026-11-02-sensor-calibration/backend.md) changelogs.

## Configuration

Copying [api/.env.example](api/.env.example) supplies the required session TTL,
seat count and publisher limit. Backend settings use `DROWSINESS_`; shell
variables override `api/.env`. Optional frontend overrides belong in
`webui/.env.local`. Restart after changing settings.

The [MobileNetV4 checkpoint](api/models/README.md) is included. Device `auto`
prefers CUDA, then Apple MPS, then CPU. MPS needs native macOS; CUDA needs
compatible NVIDIA hardware and a CUDA-enabled PyTorch installation. Keep one API
process.

Camera access needs localhost or trusted HTTPS. For remote cameras, set both
`DEV_TLS_CERT` and `DEV_TLS_KEY` in `webui/.env.local` and add the exact HTTPS
origin to `DROWSINESS_ALLOWED_ORIGINS`. Certificate paths resolve from `webui/`;
use Linux paths in WSL. Do not commit private keys or credentials.

### ngrok access

Keep the API running on port 8000 and the web UI running on port 3000, then
expose only the web UI:

```powershell
ngrok http 3000
```

Vite proxies `/api` HTTP, SSE, and Socket.IO traffic to the API at port 8000, so
the backend does not need a separate ngrok tunnel. Open the HTTPS forwarding URL
shown by ngrok, for example:

```text
https://friction-bunny-stove.ngrok-free.dev/streaming
```

Set the exact HTTPS origin in `api/.env` and restart the API:

```dotenv
DROWSINESS_ALLOWED_ORIGINS=["https://friction-bunny-stove.ngrok-free.dev"]
```

The origin is the scheme and host only, without a path. Restart ngrok and update
this setting whenever the ngrok free URL changes.

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
as awake. A sample counts as drowsy only when both the sensor and camera indicate
drowsiness; missing camera measurements do not confirm a drowsy sensor reading.
Missing evidence and unoccupied seats do not count. New sensor readings can revise
the latest combined sample without adding observations. The rolling minute uses
the latest picture per second and requires ten valid samples with at least half
drowsy.

Results publish at QoS 1 to `drowsy/stud/<seat_id>/result` as `{"drowsy":true}`.
Student nodes alert for five seconds on false-to-true transitions. Sensor-driven
publications occur at most once per second, except alert changes. The lecturer
receives retained `{"drowsy_seats":[1,3]}` on `drowsy/lect/result`; empty lists clear
its display. The old hardcoded A1 notification is removed. The UI publication
indicator is per-seat and confirms broker publication, not hardware execution.

Set `DROWSINESS_MQTT_ENABLED=false` to disable MQTT or configure
`DROWSINESS_MQTT_HOST` and `DROWSINESS_MQTT_PORT`. Connections retry broker failures
and refresh current status after reconnect. Camera uploads use Socket.IO.

See the [calibration guide](docs/sensor-calibration.md) for recording, training, rehearsal,
activation and rollback. Calibration data persists locally; live history remains
in memory. Rehearsal is a one-second diagnostic, stores no images, and candidate
comparisons do not trigger hardware alerts.

## Checks

Run backend checks from `api/`:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
node --test scripts/k6/streaming.test.mjs
```

Run frontend checks from `webui/`:

```bash
npm run typecheck
npm run lint
npm run check
npm run test
npm run build
```

Run `npm run test:e2e` from `webui/` with both apps running and Chrome installed.

## Add another project

1. Create a sibling directory with a descriptive name, such as `firmware/`,
   `training/`, or `analytics/`. Put the actual project source there.
2. Keep its dependency manifest, lockfile, tests, configuration examples, and
   README inside that directory. Document commands relative to that directory.
3. Add project-specific ignore rules for generated output. The root `.gitignore`
   already covers common environments, caches, dependency directories, and secrets.
4. Add the project to the table above and document its checks in its own README.

Projects communicate through explicit interfaces such as HTTP, Socket.IO, or
MQTT. Keep source code and environments independent; introduce shared packages
when multiple projects actually need the same code.

## Existing checkout after the move

The backend's `pyproject.toml`, `uv.lock`, `.python-version`, `.env.example`, model
checkpoint, scripts, and Compose configuration now live under `api/`. Run
`uv sync --locked` from `api/` to create `api/.venv`; an old root `.venv` is no longer used by the
documented commands. Keep an existing backend `.env` at `api/.env`. Update IDE run
configurations to use `api/` as the working directory and `main:app` as the ASGI
entry point. Python imports stay local to the API project (`core` and `modules`).
