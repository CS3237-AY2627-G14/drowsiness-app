# Readability conventions

- Name dependencies after their abstractions, such as `room_repository`,
  `sessions_facade` and `processing_registry`. Prefer explicit names over ambiguous shorthand.

- Inject runtime operations through typed objects with named methods, such as
  `clock.now()` and `frame_predictor.predict_batch(...)`. Keep callable factories
  in application wiring and callbacks required by framework APIs.
- Name intermediate values instead of nesting operational calls. Keep simple
  builtins, framework declarations and conventional utility composition readable.
- Extract helpers for meaningful tasks and prefer verb-first names; use `is`,
  `has` or `can` for predicates. Avoid wrappers around obvious single operations.
- Preserve established component, hook, fixture and utility conventions, including
  `cn` and its implementation. Keep helpers local to their consumers.

# Backend conventions

Read `docs/architecture.md` before changing module boundaries.

- Preserve the existing frontend scaffold unless the task involves frontend work.
- Use router → facade → service → repository. Facades delegate; services own rules.
- Cross-module imports must target `modules.<name>.facade` exclusively. Re-export
  public immutable DTOs and errors there with explicit `__all__`.
- Allowed dependencies: classrooms → none; sessions → classrooms;
  streaming → sessions, processing; processing → none;
  devices → classrooms, sessions. Keep dependencies acyclic.
- `core` cannot import business modules. Only application wiring and tests may
  import another module's implementation directly.
- Services must not depend on FastAPI or SQLAlchemy. Repositories must not depend
  on HTTP. Keep ORM objects and storage collections internal.
- Inject dependencies through constructors and resolve HTTP dependencies with
  FastAPI `Depends`. Initialize in-memory stores once during application lifespan.
- Use typed Pydantic records, SQLAlchemy `Mapped` annotations, explicit return
  types, absolute imports, and UTC-aware timestamps.
- Keep comments brief. Use module-local `utils.py` or a focused `utils/` package
  for small pure helpers with related responsibilities; keep business logic in
  services.
- Models describe schema only. Never run `create_all`, generate migrations, or
  apply migrations during application startup. Future Alembic revisions and
  upgrades must be separate, explicit commands.
- Never log tokens, passwords, complete auth payloads, or credential-bearing URLs.
- Run `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, and
  `uv run pytest` after backend changes. Do not introduce placeholder services or
  generic base repositories for unimplemented features.

# Frontend conventions

- Use arrow functions for frontend functions, components, hooks, and test helpers.
- Read `docs/architecture.md` before changing frontend boundaries.
- Use static TanStack Router configuration in `webui/src/router.tsx`.
- Pages belong to their feature. Each page has a PascalCase folder/file; all
  components and component exports use PascalCase. Hooks use `useCamelCase`.
- Keep page-only components/hooks/utils in the page folder. Promote code to shared
  folders only when it has shared consumers.
- Keep `api/` as typed HTTP adapters, without UI state or publishing policy.
- Use the shared Axios instance in `webui/src/lib/axiosClient.ts` for HTTP requests.
- Keep camera/peer/timer handles out of React state. Clean up on stop/unmount.
- Preserve the whole camera frame with padding. No client-side cropping/inference.
- Do not persist or log credentials, SDP, or complete authorization payloads.
- Run frontend typecheck, lint, tests, build, and React Doctor after React changes.
