# Monorepo conventions

- Each top-level project owns its dependencies, lockfile, configuration, tests,
  and README. Current projects are `api/` and `webui/`.
- Run project commands from that project's directory using its own tooling.
- Keep Python imports local to the API (`core`, `modules`, `tests`); `api/` is a
  project directory, not a Python import namespace.
- Read project-specific `AGENTS.md` files before changing their code.
- Add new projects as sibling directories and document their setup in their own
  README and in the root project table. Do not introduce cross-project source
  imports or shared dependencies without an actual consumer.
- Keep credentials, generated outputs, and local environments out of Git.
