# Merge integration and calibration boundary

The merge combines camera selection, learned sensor calibration and per-seat
MQTT results. Student nodes now use one versioned raw protocol on
`drowsy/stud/<seat_id>/data`; reflash all nodes together. Combined detections
use live sensor evidence, and sensor changes revise the latest sample without
adding observations. The lecturer consumes retained actual seat lists, replacing
the hardcoded A1 notification. Both firmware setup guides describe the new flow.

Calibration is now a sibling API module. It owns recording, labels, training,
evaluation and persisted selection; processing owns live classification, loaded
models, inference and alerts. Calibration imports processing's public facade;
processing receives a typed measurement recorder through application wiring.

Initialize storage with `uv run python -m modules.calibration init` from `api/`.
The existing database and artifact formats are preserved. Rehearsal JSON gains
optional sensor updates and generation metadata; old recordings remain readable.
Reports remain diagnostics at one-second resolution, not complete event traces.

Historical changelogs describe the original branch implementation. This note and
the current project READMEs supersede their old topic, command and timing details.

Arduino CLI and physical nodes were unavailable during integration. Firmware
compilation and physical MQTT, LCD, LED and buzzer behavior remain unverified.
