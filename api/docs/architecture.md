# Architecture

A modular monolith: a FastAPI API and a React frontend in `../../webui`. [main.py](../main.py)
wires the application together.

## Modules

| Module | Responsibility | Allowed dependencies |
| --- | --- | --- |
| classrooms | Rooms and seats | None |
| sessions | Authorization sessions and exclusive publisher ownership | Classrooms facade |
| streaming | Live connections, frame admission, lifecycle and reporting | Sessions and processing facades |
| processing | Frame and sensor processing, inference scheduling and detection history | None |
| calibration | Recording, labels, training, evaluation and persisted model selection | Processing facade |
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
- **Processing** analyzes frames and seat sensor readings and holds detection
  results. It knows only connections, seat IDs and measurements, never
  authorization, sessions or classrooms.

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
   Raw four-sensor MQTT readings update per-seat state. Processing owns the
   28-row sensor truth table, presence, camera fusion and rolling minute alerts.
   Student nodes only acquire readings and execute per-seat alert commands.
   Fresh readings attach to camera samples; sensor updates may reclassify the
   latest sample without adding observations. Per-seat status and retained
   lecturer seat lists drive the student and lecturer firmware.
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

## Persistent sensor calibration

Processing owns live telemetry, temporal features, loaded models, fusion and alerts.
The sibling calibration module owns recording/label storage, grouped validation,
training jobs and persisted model selection. Its router delegates through its
facade to services and a SQLite repository. Calibration depends only on the
processing facade; processing never imports calibration. Application wiring
injects a typed MeasurementRecorder implemented by calibration RecordingService.
The browser accesses HTTP/SSE endpoints under `/api/calibration`.

Initialize SQLite separately with `python -m modules.calibration init`.
Startup only reads existing schema, recovers interrupted jobs/recordings, and
loads the selected artifact. Rooms, authorization, and connections remain
in memory; calibration recordings, revisions, snapshots, and model selection
persist in the configured local data directory. Keep one API process.

Raw telemetry contains all four readings plus boot identity, sequence, and uptime.
Server receipt time aligns recordings and rehearsals. The same two-second feature
extraction is used online and during training. Validation splits entire recordings,
including preprocessing; reserved recordings never affect fitting or threshold
selection. Training runs outside the event loop and never activates automatically.

Before activation the corrected legacy rules remain available. After activation
raw telemetry owns seat 1's gate, and missing evidence stays unknown. Current sensor evidence is applied after inference; new readings revise only
the latest combined sample without adding observations. Activation clears sensor and
detection history and invalidates outstanding results from the previous model
generation while keeping publisher ownership.

Rehearsal recording stores camera measurements and snapshots of active, legacy,
and candidate gates, without images. Counterfactual replay uses the same fusion
and rolling-alert rules; only the active live path publishes hardware alerts.
See [the operator guide](../../docs/sensor-calibration.md).

## Frontend

The browser captures and publishes camera frames over the streaming socket.
Connection and encoding errors stop publishing but keep the local camera preview
available for retry.
