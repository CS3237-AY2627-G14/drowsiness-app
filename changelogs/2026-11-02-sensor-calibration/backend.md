# Backend changes — 2026-11-02

## Calibration and persistence

- Added processing-owned calibration router, facade, services, typed records,
  SQLite repository, temporal features, training, and rehearsal reporting.
- Added explicit `uv run python -m modules.processing.calibration init` setup.
  A separate `reset-selection` command recovers a failed selected-artifact load
  without deleting recordings or model history.
  Startup never creates or migrates schema; it reads selection and marks
  interrupted recordings/jobs closed/failed.
- Added `.local/calibration` storage, configurable directory and occupancy
  distance, persistent label revisions, dataset snapshots, artifacts, and reports.
- Added `/api/calibration` recording/label/export APIs, live HTTP/SSE state,
  training jobs, model reports, selection/rollback, and rehearsal comparison.

## Learning and live integration

- Added locked scikit-learn/joblib dependencies. Compare depth-5 tree and
  100-tree forest with legacy and always-positive baselines.
- Extract trailing two-second sensor median, interquartile range, change, and
  valid fraction; require eight valid packets and update predictions once per second.
- Fit imputation within each recording-level validation fold. Weight episodes
  equally and select thresholds for ≥95% validation recall with minimum awake
  false positives. Reserved recordings affect neither fitting nor selection.
- Save dataset identity, feature/library configuration, threshold, and reports.
  Training runs outside the event loop and cannot automatically activate.
- Accept `drowsy:-1` as unknown, replacing previous evidence immediately. After
  activation, raw telemetry owns seat 1; legacy packets cannot overwrite it.
- Snapshot evidence at camera admission. Activation/rollback clears sensor and
  rolling history and drops outstanding previous-model results.
- Extend streaming status with sensor score, model version, and unavailable reason.
- Store rehearsal camera measurements and gate snapshots without images; replay
  fused false alerts per awake minute and alert onset latency. Candidate results
  do not enter the hardware alert publisher.

## Tests and operations

Added tests for telemetry contracts, missing echoes, window resets, feature parity,
label boundaries, threshold tradeoffs, grouped validation, held-out reports,
recording/revision persistence, interrupted-state recovery, background training,
activation/restart, authoritative raw input, sensor snapshots, rehearsal comparison,
and HTTP initialization/export behavior.

See the [system changelog](system.md) for final verification results and platform
limits, the [API README](../../api/README.md) for configuration, and the
[operator guide](../../docs/sensor-calibration.md) for usage and recovery.
