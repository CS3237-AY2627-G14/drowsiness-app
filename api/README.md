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
