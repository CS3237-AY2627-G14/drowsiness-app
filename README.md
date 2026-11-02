# Drowsiness detection monorepo

The API and camera client live in independent projects in one repository. Add
other project code as sibling directories, using the tooling suited to each one.

| Project | Purpose | Tooling | Documentation |
| --- | --- | --- | --- |
| [`api/`](api/) | FastAPI backend, inference, and local MQTT broker configuration | Python 3.12, uv, Docker Compose | [API guide](api/README.md) |
| [`student-node-v1/`](student-node-v1/) | Raw sensor acquisition and alert actuator | Arduino ESP32 | [Firmware guide](student-node-v1/README.md) |
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
uv run uvicorn main:app --host 0.0.0.0 --port 8000
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

## MQTT

Mosquitto listens on the Docker host's port 1883. Student nodes publish raw JSON
to `drowsy/stud/<seat_id>/data`; `drowsy/student<N>/data` and
`wakey/student<N>/sensors` remain accepted aliases:

```json
{"upper_cm":7,"lower_mm":150,"back_raw":1000,"desk_raw":1500}
```

Distances use -1 for an invalid reading; ADC values range from 0 to 4095.
The base derives presence and the nullable sensor result using the original
28-row truth table. ToF below 300 mm indicates presence. Ultrasonic levels split
at 5 and 9 cm, backrest levels at 0 and 3000, and desk levels at 1000 and 2000.
An absent seat or a desk reading below 1000 produces no result.

Fresh sensor results (at most five seconds old) are fused with camera frames.
A drowsy sensor result counts if the camera agrees or has no face measurements;
an awake camera result overrides it. An awake sensor result counts as awake.
Unavailable or stale readings do not count. The rolling minute uses the latest
picture per second and requires 10 valid samples, at least half drowsy.
Sensor updates reclassify the latest sample without adding observations.

The base publishes `{"drowsy":true}` to `drowsy/stud/<seat_id>/result`.
Student nodes run their five-second alert on a false-to-true transition.
Sensor-driven status publishes at most once per second, except alert changes.
Changes to the alert set publish retained `{"drowsy_seats":[1,3]}` messages to
`drowsy/lect/result`. The legacy lecturer notification remains
`{"id":"A1"}` on `drowsy/result` at QoS 1; its seat label is still hardcoded.
The live status indicates successful legacy publication within ten seconds.

Set `DROWSINESS_MQTT_ENABLED=false` to disable MQTT, or configure
`DROWSINESS_MQTT_HOST` and `DROWSINESS_MQTT_PORT`. Clients retry broker failures.
Camera uploads continue over Socket.IO.

From `api/`, publish ten raw readings with:

```bash
uv run python tests/test_publish_mqtt_test_data.py
uv run python tests/test_publish_mqtt_test_data.py --lower-mm -1
```

Deploy the API and reflash students together: summarized drowsy/present inputs
are no longer accepted. See the student firmware README for setup.

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
