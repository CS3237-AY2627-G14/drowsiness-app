import asyncio
from typing import Any

from core.clock import Clock, SystemClock
from core.config import Settings
from modules.processing.schemas import (
    LiveTelemetry,
    RawTelemetry,
    SensorMeasurements,
    StoredSample,
)
from modules.processing.sensor_features import SensorWindow, baseline_result
from modules.processing.sensor_models import load_artifact, predict_scores
from modules.processing.services.sensor_classification import classify_presence


class SensorClassificationService:
    def __init__(self, settings: Settings, clock: Clock | None = None) -> None:
        self._settings = settings
        self._clock = clock if clock is not None else SystemClock()
        self._window = SensorWindow()
        self._latest: StoredSample | None = None
        self._active_model: str | None = None
        self._artifact: dict[str, Any] | None = None
        self._candidate_model: str | None = None
        self._candidate: dict[str, Any] | None = None
        self._retired_boots: set[str] = set()
        self._evidence: SensorMeasurements | None = None
        self._candidate_score: float | None = None
        self._last_prediction = -1.0
        self._lock = asyncio.Lock()

    def now(self) -> float:
        return self._clock.now().timestamp()

    async def receive_telemetry(self, telemetry: RawTelemetry) -> bool:
        async with self._lock:
            if telemetry.boot_id in self._retired_boots:
                return False
            if self._latest is not None:
                previous = self._latest.telemetry
                if telemetry.boot_id == previous.boot_id:
                    if (
                        telemetry.sequence <= previous.sequence
                        or telemetry.uptime_ms <= previous.uptime_ms
                    ):
                        return False
                else:
                    self._retired_boots.add(previous.boot_id)
                    self._evidence = None
                    self._last_prediction = -1.0
            sample = StoredSample(received_at=self.now(), telemetry=telemetry)
            if self._latest and sample.received_at - self._latest.received_at > 0.6:
                self._evidence = None
                self._candidate_score = None
                self._last_prediction = -1.0
            self._latest = sample
            self._window.add(sample)
            present = classify_presence(telemetry, self._settings.sensor_presence_mm)
            if present is not True:
                self._evidence = SensorMeasurements(
                    drowsy=None,
                    captured_at_ms=sample.received_at * 1000,
                    present=False,
                    model_version=self._active_model,
                    unavailable_reason="unoccupied",
                )
                return True
            if (
                self._artifact is None
                or sample.received_at - self._last_prediction >= 1
            ):
                self._last_prediction = sample.received_at
                self._predict(sample)
            return True

    def _predict(self, sample: StoredSample) -> None:
        features = self._window.features()
        self._candidate_score = (
            predict_scores(self._candidate["estimator"], [features])[0]
            if self._candidate is not None and features is not None
            else None
        )
        score: float | None = None
        possible: bool | None = None
        reason: str | None = None
        if self._artifact is not None:
            if features is None:
                reason = "insufficient_valid_window"
            else:
                score = predict_scores(self._artifact["estimator"], [features])[0]
                possible = score >= self._artifact["threshold"]
        else:
            possible = baseline_result(sample, self._settings.sensor_presence_mm)
            if possible is None:
                reason = "legacy_no_result"
        self._evidence = SensorMeasurements(
            drowsy=possible,
            captured_at_ms=sample.received_at * 1000,
            present=True,
            score=score,
            model_version=self._active_model,
            unavailable_reason=reason,
        )

    def get_sensor_evidence(self) -> SensorMeasurements:
        if (
            self._evidence is None
            or self.now() - self._evidence.captured_at_ms / 1000
            > self._settings.mqtt_sensor_max_age_seconds
        ):
            return SensorMeasurements(
                drowsy=None,
                present=None,
                captured_at_ms=self.now() * 1000,
                model_version=self._active_model,
                unavailable_reason="telemetry_stale_or_warming_up",
            )
        return self._evidence

    def get_live_telemetry(self) -> LiveTelemetry:
        evidence = self.get_sensor_evidence()
        return LiveTelemetry(
            sample=self._latest,
            age_seconds=max(0, self.now() - self._latest.received_at)
            if self._latest
            else None,
            active_model=self._active_model,
            candidate_model=self._candidate_model,
            score=evidence.score,
            candidate_score=self._candidate_score
            if evidence.unavailable_reason != "telemetry_stale_or_warming_up"
            else None,
            possible_drowsy=evidence.drowsy,
            present=evidence.present,
            unavailable_reason=evidence.unavailable_reason,
        )

    def get_sensor_comparisons(self) -> dict[str, SensorMeasurements]:
        evidence = self.get_sensor_evidence()
        baseline = (
            baseline_result(self._latest, self._settings.sensor_presence_mm)
            if self._latest
            else None
        )
        if evidence.unavailable_reason == "telemetry_stale_or_warming_up":
            baseline = None
        candidate = (
            self._candidate_score >= self._candidate["threshold"]
            if self._candidate_score is not None
            and self._candidate is not None
            and evidence.present is True
            and evidence.unavailable_reason != "telemetry_stale_or_warming_up"
            else None
        )
        return {
            "active": evidence,
            "baseline": evidence.model_copy(
                update={"drowsy": baseline, "model_version": None}
            ),
            "candidate": evidence.model_copy(
                update={"drowsy": candidate, "model_version": self._candidate_model}
            ),
        }

    async def load_model(
        self, model_id: str | None, *, candidate: bool = False
    ) -> None:
        artifact = None
        if model_id is not None:
            artifact = await asyncio.to_thread(
                load_artifact,
                self._settings.calibration_directory.resolve(),
                model_id,
                self._settings.sensor_presence_mm,
            )
        if candidate:
            self._candidate = artifact
            self._candidate_model = model_id
            self._candidate_score = None
            return
        self._artifact = artifact
        self._active_model = model_id
        self._window.clear()
        self._evidence = None
        self._last_prediction = -1.0
        self._candidate_score = None
