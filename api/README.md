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

Mosquitto publishes `127.0.0.1:1883` on the Docker host with anonymous local access. State is
in memory and lost on restart. Use `docker compose logs -f mqtt` for logs.
The API subscribes to `drowsy/+/data` and `wakey/+/sensors`; topics named
`drowsy/student<N>/data` or `wakey/student<N>/sensors` map readings to seat N.
Messages are UTF-8 JSON with `drowsy` and `present` encoded as `0` or `1`. The
API timestamps each message when it receives it and attaches fresh results to
that seat's camera detections. The ESP32 determines sensor drowsiness: when it
reports drowsy, the combined sample is drowsy if the camera agrees or detects
no face; a camera result showing an awake face overrides it. Unoccupied or
stale sensor results do not count. Set `DROWSINESS_MQTT_ENABLED=false` to disable
MQTT input and output, or override `DROWSINESS_MQTT_HOST` and
`DROWSINESS_MQTT_PORT`. The subscriber and result publisher retry when the broker
is unavailable. When the drowsiness alert turns on, the API publishes
`{"id": "A1"}` to `drowsy/result` at QoS 1; `B1` will be added later. Camera
uploads continue to use Socket.IO at `/api/socket.io` through Vite's API proxy.

For a local test publisher and the full sensor behavior details, see the
[MQTT guide](../README.md#mqtt).

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
