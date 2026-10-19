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
MQTT application integration is not implemented yet; camera uploads use Socket.IO.

API configuration belongs in `api/.env`; frontend configuration belongs in
`webui/.env` or `webui/.env.local`. Preserve existing environment files during setup.

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
