# Drowsiness detection monorepo

The API and camera client live in independent projects in one repository. Add
other project code as sibling directories, using the tooling suited to each one.

| Project | Purpose | Tooling | Documentation |
| --- | --- | --- | --- |
| [`api/`](api/) | FastAPI backend, inference, and local MQTT broker configuration | Python 3.12, uv, Docker Compose | [API guide](api/README.md) |
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

Mosquitto publishes `127.0.0.1:1883` on the Docker host with anonymous local access.
State is in memory and lost on restart. Use `docker compose logs -f mqtt` for logs.
The API subscribes to `drowsy/+/data` and the firmware topic
`wakey/+/sensors`; `student<N>` maps to seat N. Messages are UTF-8 JSON with
`drowsy` and `present` encoded as `0` or `1`. The ESP32 determines the sensor
drowsiness result; the API combines it with the camera result and timestamps
each message when received:

```json
{"drowsy": 1, "present": 1}
```

The latest sensor result is attached to that seat's camera detection when it
is no more than five seconds old. A sample for an unoccupied seat or without a
fresh sensor result is not counted. If the ESP32 reports drowsiness, the sample
counts as drowsy when the camera also detects drowsiness or detects no face; a
camera result showing an awake face overrides the ESP32 result. Set
`DROWSINESS_MQTT_ENABLED=false` to disable MQTT input and output, or override
`DROWSINESS_MQTT_HOST` and `DROWSINESS_MQTT_PORT` to use another broker.
The subscriber and result publisher retry if the broker is unavailable. When
the drowsiness alert turns on, the API publishes `{"id": "A1"}` to
`drowsy/result` at QoS 1. Seat identifiers are hardcoded for now; `B1` will be
added later. Camera uploads continue to use Socket.IO at `/api/socket.io`
through Vite's API proxy.

To send a test reading to the local broker while the API and frontend are
running, start a camera stream for seat 1 and run this from `api/`:

```bash
cd api
uv run python tests/test_publish_mqtt_test_data.py
```

The script publishes ten fresh test results (one per second) to
`wakey/student1/sensors`. Check the ESP32 result and the combined camera
classification in live detection status. Change the node, drowsy/present flags,
count, or interval with its options. For example, test an unoccupied seat:

```bash
cd api
uv run python tests/test_publish_mqtt_test_data.py --student 2 --drowsy 0 --present 0
```

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
