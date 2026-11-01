import asyncio
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from core.config import Settings
from main import create_app
from modules.processing.calibration.features import SensorWindow, baseline_result
from modules.processing.calibration.repository import (
    CalibrationRepository,
    initialize_database,
)
from modules.processing.calibration.schemas import (
    LabelInterval,
    RawTelemetry,
    Recording,
    RecordingDetail,
    RecordingRequest,
    StoredSample,
)
from modules.processing.calibration.service import CalibrationService
from modules.processing.calibration.training import (
    build_rows,
    load_artifact,
    predict_scores,
    train_model,
    tune_threshold,
)
from modules.processing.facade import ProcessingFacade
from modules.processing.inference.frame_buffer import FrameBuffer
from modules.processing.mqtt_router import SensorMqttRouter
from modules.processing.repositories.registry import InMemoryProcessingRegistry
from modules.processing.schemas import FrameInput, FrameMeasurements, SensorMeasurements
from modules.processing.services.frame_processing_service import FrameProcessingService
from tests.helpers import FakeFramePredictor, MutableClock, fake_inference_runtime


def raw(
    sequence: int = 1, boot: str = "boot-a", upper: int | None = 12
) -> RawTelemetry:
    return RawTelemetry(
        schema_version=1,
        boot_id=boot,
        sequence=sequence,
        uptime_ms=sequence * 200,
        upper_cm=upper,
        lower_mm=180,
        back_adc=2200,
        desk_adc=1500,
    )


def dataset(index: int, held_out: bool = False) -> RecordingDetail:
    start = float(1000 + index * 100)
    return RecordingDetail(
        recording=Recording(
            id=f"recording-{index}",
            participant="test",
            started_at=start,
            stopped_at=start + 44,
            role="held_out" if held_out else "development",
        ),
        samples=[
            StoredSample(
                received_at=start + sequence / 5,
                telemetry=raw(sequence, upper=2 if sequence < 110 else 15),
            )
            for sequence in range(220)
        ],
        intervals=[
            LabelInterval(
                start=start, end=start + 22, label="awake", posture="upright"
            ),
            LabelInterval(
                start=start + 22, end=start + 44, label="drowsy", posture="head down"
            ),
        ],
    )


@pytest.mark.parametrize(
    "change",
    [
        {"upper_cm": -1},
        {"schema_version": 2},
        {"desk_adc": 5000},
        {"back_adc": True},
        {"lower_mm": 0},
        {"extra": 1},
    ],
)
def test_raw_contract_rejects_invalid_measurements(change: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        RawTelemetry.model_validate({**raw().model_dump(), **change})


def test_features_handle_missing_echo_and_reset_windows() -> None:
    window = SensorWindow()
    for index in range(10):
        window.add(
            StoredSample(received_at=index / 5, telemetry=raw(index, upper=None))
        )
    features = window.features()
    assert features is not None and features[3] == 0
    assert baseline_result(window.samples[-1]) is None
    window.add(StoredSample(received_at=2.0, telemetry=raw(1, boot="new")))
    assert window.features() is None and len(window.samples) == 1
    window.add(StoredSample(received_at=8.0, telemetry=raw(2, boot="new")))
    assert len(window.samples) == 1


def test_dataset_features_match_online_and_exclude_label_boundaries() -> None:
    detail = dataset(0)
    rows = build_rows([detail])
    window = SensorWindow()
    for sample in detail.samples[:11]:
        window.add(sample)
    assert rows.features[0] == window.features()
    assert set(rows.groups) == {detail.recording.id}
    assert rows.labels.count(0) == rows.labels.count(1)
    detail.intervals[0].label = "uncertain"
    assert set(build_rows([detail]).labels) == {1}


def test_threshold_preserves_labels_and_prefers_recall() -> None:
    threshold, metrics = tune_threshold([0, 1, 0, 1], [0.1, 0.2, 0.2, 0.9])
    assert threshold == 0.2
    assert metrics["recall"] == 1
    assert metrics["awake_false_positive_rate"] == 0.5


def test_grouped_training_artifact_and_held_out_report(tmp_path: Path) -> None:
    details = [dataset(index, held_out=index == 3) for index in range(4)]
    model_id = uuid4().hex
    report = train_model(details, model_id, tmp_path)
    assert report["validation_groups"] == ["recording-0", "recording-1", "recording-2"]
    assert report["held_out"]["metrics"]["recall"] == 1
    assert report["held_out"]["metrics"]["awake_false_positive_rate"] == 0
    artifact = load_artifact(tmp_path, model_id)
    scores = predict_scores(artifact["estimator"], build_rows([details[3]]).features)
    assert len(scores) > 20 and min(scores) == 0 and max(scores) == 1
    with pytest.raises(ValueError, match="identifier"):
        load_artifact(tmp_path, "../escape")
    with pytest.raises(ValueError, match="three"):
        train_model(details[:2], uuid4().hex, tmp_path)


def test_recording_deduplication_labels_persistence_and_recovery(
    tmp_path: Path,
) -> None:
    async def run() -> None:
        clock = MutableClock()
        repository = CalibrationRepository(tmp_path)
        service = CalibrationService(repository, Settings(), clock)
        await service.start()
        assert not service.ready
        assert not await asyncio.to_thread(repository.path.exists)
        with pytest.raises(RuntimeError):
            await service.start_recording(RecordingRequest(participant="a"))
        initialize_database(tmp_path)
        await service.start()
        recording = await service.start_recording(RecordingRequest(participant="a"))
        await service.receive(raw())
        await service.receive(raw())
        clock.current_time += timedelta(seconds=0.2)
        await service.receive(raw(2))
        clock.current_time += timedelta(seconds=0.2)
        await service.receive(raw(1, boot="new"))
        await service.receive(raw(99))  # retired boot cannot return
        detail = await service.detail(recording.id)
        assert len(detail.samples) == 3
        end = clock.now().timestamp()
        interval = LabelInterval(start=recording.started_at, end=end, label="awake")
        await service.label(recording.id, [interval])
        with pytest.raises(ValueError, match="overlap"):
            await service.label(recording.id, [interval, interval])
        await service.label(
            recording.id, [interval.model_copy(update={"label": "uncertain"})]
        )
        revisions = await repository.query("SELECT COUNT(*) FROM label_revisions")
        assert revisions[0][0] == 2
        restarted = CalibrationService(repository, Settings(), clock)
        await restarted.start()
        recovered = await restarted.detail(recording.id)
        assert recovered.recording.stopped_at is not None
        assert recovered.intervals[0].label == "uncertain"
        clock.current_time += timedelta(seconds=6)
        assert service.evidence().drowsy is None

    asyncio.run(run())


def test_background_training_activation_and_restart(tmp_path: Path) -> None:
    async def run() -> None:
        initialize_database(tmp_path)
        repository = CalibrationRepository(tmp_path)
        service = CalibrationService(repository, Settings())
        await service.start()
        for index in range(3):
            detail = dataset(index)
            await repository.save_recording(detail.recording)
            await repository.add_samples(detail.recording.id, detail.samples)
            await repository.replace_labels(detail.recording.id, detail.intervals)
        job = await service.train([f"recording-{index}" for index in range(3)])
        assert job.status == "running" and service.live().active_model is None
        await service.receive(raw())  # ingestion remains available during training
        await service.stop()
        assert (await service.jobs())[0].status == "complete"
        await service.activate(job.id)
        assert (
            service.live().active_model == job.id and service.evidence().drowsy is None
        )
        restarted = CalibrationService(repository, Settings())
        await restarted.start()
        assert restarted.live().active_model == job.id
        await restarted.activate(None)
        assert await repository.get_selection() is None

    asyncio.run(run())


def test_legacy_unknown_invalidates_and_frames_snapshot_sensor_evidence() -> None:
    async def run() -> None:
        buffer = FrameBuffer()
        frames = FrameProcessingService(
            InMemoryProcessingRegistry(), buffer, FakeFramePredictor(), Settings()
        )
        connection_id = uuid4()
        await frames.open_connection(connection_id)
        await frames.associate_seat(connection_id, 1)
        await frames.submit_sensor_measurements(
            1, SensorMeasurements(drowsy=True, present=True, captured_at_ms=1.0)
        )
        await frames.submit_frame(
            connection_id, FrameInput(frame_id=1, captured_at_ms=1.0, jpeg=b"jpeg")
        )
        router = SensorMqttRouter(Settings(), ProcessingFacade(frames))
        await router._handle_message(
            "drowsy/student1/data", b'{"drowsy":-1,"present":1}'
        )
        await frames.submit_frame(
            connection_id, FrameInput(frame_id=2, captured_at_ms=2.0, jpeg=b"jpeg")
        )
        batch = buffer.claim_batch(1)
        assert batch[0].sensor is not None and batch[0].sensor.drowsy is None
        assert batch[0].sensor.unavailable_reason == "legacy_no_result"
        buffer.release_batch(batch)
        await frames.submit_sensor_measurements(
            1, SensorMeasurements(drowsy=True, present=True, captured_at_ms=9e15)
        )
        await frames.submit_frame(
            connection_id, FrameInput(frame_id=3, captured_at_ms=3.0, jpeg=b"jpeg")
        )
        batch = buffer.claim_batch(1)
        await frames.submit_sensor_measurements(
            1, SensorMeasurements(drowsy=False, present=True, captured_at_ms=9e15 + 1)
        )
        assert batch[0].sensor is not None and batch[0].sensor.drowsy is True
        frames._apply_frame_measurements(
            FrameMeasurements(
                connection_id=connection_id,
                frame_id=3,
                captured_at_ms=3.0,
                left_ear=0.1,
                right_ear=0.1,
            ),
            batch[0].sensor,
        )
        generation = batch[0].generation
        await frames.reset_sensor_history()
        assert frames._generation != generation
        status = await frames.get_status(connection_id)
        assert status.detection is None and status.processed_frames == 1

    asyncio.run(run())


def test_http_recording_export_and_uninitialized_storage(tmp_path: Path) -> None:
    settings = Settings(calibration_directory=tmp_path, mqtt_enabled=False)
    app = create_app(settings, inference_factory=fake_inference_runtime)
    with TestClient(app) as client:
        assert client.get("/api/calibration/live").json()["storage_ready"] is False
        assert client.get("/api/calibration/recordings").status_code == 503
    initialize_database(tmp_path)
    with TestClient(app) as client:
        created = client.post("/api/calibration/recordings", json={"participant": "A"})
        assert created.status_code == 201
        identifier = created.json()["id"]
        assert (
            client.post(f"/api/calibration/recordings/{identifier}/stop").status_code
            == 200
        )
        exported = client.get(f"/api/calibration/recordings/{identifier}/export")
        assert "received_at,boot_id,sequence" in exported.text
        assert (
            client.get(f"/api/calibration/recordings/{identifier}/rehearsal").json()[
                "camera_observations"
            ]
            == 0
        )
        assert (
            client.post(
                "/api/calibration/selection", json={"model_id": "missing"}
            ).status_code
            == 409
        )


def test_rehearsal_persists_counterfactual_alerts_without_images(
    tmp_path: Path,
) -> None:
    async def run() -> None:
        initialize_database(tmp_path)
        clock = MutableClock()
        service = CalibrationService(CalibrationRepository(tmp_path), Settings(), clock)
        await service.start()
        recording = await service.start_recording(
            RecordingRequest(participant="rehearsal")
        )
        connection_id = uuid4()
        for index in range(12):
            timestamp = service.now()
            positive = SensorMeasurements(
                drowsy=True, present=True, captured_at_ms=timestamp * 1000
            )
            service.observe_camera(
                recording.id,
                timestamp,
                FrameMeasurements(
                    connection_id=connection_id,
                    frame_id=index + 1,
                    captured_at_ms=float(index * 1000),
                ),
                {
                    "active": positive,
                    "baseline": positive,
                    "candidate": positive.model_copy(update={"drowsy": False}),
                },
            )
            clock.current_time += timedelta(seconds=1)
        await service.stop_recording(recording.id)
        await service.label(
            recording.id,
            [
                LabelInterval(
                    start=recording.started_at, end=service.now(), label="awake"
                )
            ],
        )
        report = await service.rehearsal(recording.id)
        assert report["camera_observations"] == 12
        assert report["comparisons"]["active"]["false_alert_activations"] == 1
        assert report["comparisons"]["candidate"]["false_alert_activations"] == 0
        assert "jpeg" not in (await service.detail(recording.id)).model_dump_json()

    asyncio.run(run())


def test_active_model_owns_raw_input_and_missing_echo_is_not_low(
    tmp_path: Path,
) -> None:
    model_id = uuid4().hex
    initialize_database(tmp_path)
    report = train_model([dataset(index) for index in range(3)], model_id, tmp_path)

    async def run() -> None:
        from modules.processing.calibration.schemas import TrainingJob

        repository = CalibrationRepository(tmp_path)
        await repository.save_job(
            TrainingJob(id=model_id, status="complete", created_at=0, report=report)
        )
        clock = MutableClock()
        service = CalibrationService(repository, Settings(), clock)
        await service.start()
        await service.activate(model_id)
        frames = FrameProcessingService(
            InMemoryProcessingRegistry(),
            FrameBuffer(),
            FakeFramePredictor(),
            Settings(),
            calibration_service=service,
        )
        facade = ProcessingFacade(frames, service)
        router = SensorMqttRouter(Settings(), facade)
        for sequence in range(16):
            await router._handle_message(
                "drowsy/student1/raw", raw(sequence).model_dump_json().encode()
            )
            clock.current_time += timedelta(seconds=0.2)
        assert service.evidence().drowsy is True
        await router._handle_message(
            "drowsy/student1/data", b'{"drowsy":0,"present":1}'
        )
        assert frames._snapshot_sensor(1).drowsy is True
        await router._handle_message("drowsy/student1/raw", b'{"schema_version":2}')
        live = service.live()
        assert live.sample is not None
        assert live.sample.telemetry.sequence == 15
        clock.current_time += timedelta(seconds=6)
        assert frames._snapshot_sensor(1).drowsy is None
        with pytest.raises(ValueError, match="mismatch"):
            load_artifact(tmp_path, model_id, 100)

    asyncio.run(run())
