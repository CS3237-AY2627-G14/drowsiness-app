# Architecture

A modular monolith: a FastAPI API and a React frontend in `../../webui`. [main.py](../main.py)
wires the application together.

## Modules

| Module | Responsibility | Allowed dependencies |
| --- | --- | --- |
| classrooms | Rooms and seats | None |
| sessions | Authorization sessions and exclusive publisher ownership | Classrooms facade |
| streaming | Live connections, frame admission, lifecycle and reporting | Sessions and processing facades |
| processing | Frame buffering, inference scheduling and detection history | None |
| devices | Device login and seat assignment | Classrooms and sessions facades |

Dependencies must stay acyclic.

## Layers

Requests flow router → facade → service → repository. Routers handle transport,
facades delegate, services enforce rules, and repositories hold internal state. A
module's facade is its public contract: other modules see only its immutable DTOs
and errors, so internals can change freely. The import rules are in [AGENTS.md](../AGENTS.md).

## Ownership

Three identifiers carry through the system: a seat, a session (its authorization
record), and a connection (one publishing connection).

- **Sessions** decides who may publish and guarantees one publisher per seat.
- **Streaming** owns live connections and is the only module that coordinates
  sessions and processing.
- **Processing** analyzes frames and holds detection results. It knows only
  connections and frames, never authorization, sessions or classrooms.

## Design decisions

- **Dependencies expose named operations.** Services use `clock.now()`,
  `timer.now()` and `frame_predictor.predict_batch(...)` through typed interfaces.
  Clocks provide UTC-aware timestamps; timers provide monotonic seconds.
  Application wiring uses a factory to own inference startup and shutdown.
- **Upload never waits for inference.** Only the latest frame per connection
  waits for processing, and older frames are dropped. Publishing never depends on
  receiving detection messages.
- **Inference runs server-side in separate worker processes.** A worker failure
  takes processing offline and closes streams.
- **In-memory, single process.** With in-memory state, updates never yield to
  other tasks, so they need no locks. External storage or multiple API processes
  require a separate concurrency design.
- **Validate at the boundary, trust inside.** Each input is validated once where
  it enters, and internal code works with typed records. Services enforce rules
  that depend on changing state, and repositories enforce the integrity of their
  data.

## Connection lifecycle

1. **Connect.** The connection is authenticated, the seat is claimed, and
   processing state is opened. Any failure rolls back all of it.
2. **Stream.** Frames are admitted and passed to processing, and detection status
   is reported to the client.
3. **Monitor.** Each connection is checked for session expiry, processing health
   and idleness. Status reporting can be removed without affecting monitoring.
4. **Disconnect.** Seat ownership is released, connection state is discarded, and
   late results for the closed connection are dropped.

## Cleanup invariants

- Exactly one party owns the cleanup of a connection, whichever requests the
  disconnect first.
- Cleanup survives cancellation, so a seat is never left reserved.
- Shutdown closes connections first, then stops inference scheduling, then stops
  the inference workers.

## Frontend

The browser captures and publishes camera frames over the streaming socket.
Connection and encoding errors stop publishing but keep the local camera preview
available for retry.