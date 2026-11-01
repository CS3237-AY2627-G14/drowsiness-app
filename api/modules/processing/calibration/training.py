import hashlib
import json
import platform
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.tree import DecisionTreeClassifier

from modules.processing.calibration.features import (
    FEATURE_VERSION,
    SensorWindow,
    baseline_result,
)
from modules.processing.calibration.schemas import RecordingDetail


@dataclass
class TrainingRows:
    features: list[list[float]]
    labels: list[int]
    groups: list[str]
    episodes: list[str]
    postures: list[str]
    baseline: list[bool | None]
    eligible_windows: int = 0


def build_rows(details: list[RecordingDetail], presence_mm: int = 300) -> TrainingRows:
    rows = TrainingRows([], [], [], [], [], [])
    for detail in details:
        window = SensorWindow()
        previous_second = -1
        for sample in detail.samples:
            window.add(sample)
            second = int(sample.received_at)
            if second == previous_second:
                continue
            previous_second = second
            for index, interval in enumerate(detail.intervals):
                if (
                    interval.label != "uncertain"
                    and interval.start <= sample.received_at - 2
                    and sample.received_at < interval.end
                ):
                    rows.eligible_windows += 1
                    features = window.features()
                    if features is None or sample.telemetry.lower_mm is None:
                        break
                    if sample.telemetry.lower_mm >= presence_mm:
                        break
                    rows.features.append(features)
                    rows.labels.append(int(interval.label == "drowsy"))
                    rows.groups.append(detail.recording.id)
                    rows.episodes.append(f"{detail.recording.id}:{index}")
                    rows.postures.append(interval.posture or "unspecified")
                    rows.baseline.append(baseline_result(sample, presence_mm))
                    break
    return rows


def calculate_metrics(
    labels: list[int], predictions: Sequence[bool | None]
) -> dict[str, Any]:
    tp = sum(
        label == 1 and predicted is True
        for label, predicted in zip(labels, predictions, strict=True)
    )
    fn = sum(
        label == 1 and predicted is not True
        for label, predicted in zip(labels, predictions, strict=True)
    )
    fp = sum(
        label == 0 and predicted is True
        for label, predicted in zip(labels, predictions, strict=True)
    )
    tn = sum(
        label == 0 and predicted is False
        for label, predicted in zip(labels, predictions, strict=True)
    )
    negatives = labels.count(0)
    return {
        "true_positive": tp,
        "false_negative": fn,
        "false_positive": fp,
        "true_negative": tn,
        "recall": tp / (tp + fn) if tp + fn else None,
        "awake_false_positive_rate": fp / negatives if negatives else None,
        "unavailable": sum(predicted is None for predicted in predictions),
        "samples": len(labels),
    }


def create_estimator(name: str) -> Pipeline:
    classifier = (
        DecisionTreeClassifier(max_depth=5, min_samples_leaf=5, random_state=42)
        if name == "decision_tree"
        else RandomForestClassifier(
            n_estimators=100,
            max_depth=5,
            min_samples_leaf=5,
            random_state=42,
            n_jobs=1,
        )
    )
    return Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
            ("classifier", classifier),
        ]
    )


def fit_estimator(estimator: Pipeline, rows: TrainingRows, indices: list[int]) -> None:
    counts = Counter(rows.episodes[index] for index in indices)
    weights = np.asarray([1 / counts[rows.episodes[index]] for index in indices])
    weights *= len(indices) / weights.sum()
    estimator.fit(
        [rows.features[index] for index in indices],
        [rows.labels[index] for index in indices],
        classifier__sample_weight=weights,
    )


def predict_scores(estimator: Pipeline, features: list[list[float]]) -> list[float]:
    if not features:
        return []
    scores: list[float] = estimator.predict_proba(features)[:, 1].tolist()
    return scores


def tune_threshold(
    labels: list[int], scores: list[float]
) -> tuple[float, dict[str, Any]]:
    candidates = sorted(set([0.0, *scores]))
    feasible: list[tuple[float, float, dict[str, Any]]] = []
    for threshold in candidates:
        metrics = calculate_metrics(labels, [score >= threshold for score in scores])
        if metrics["recall"] >= 0.95:
            feasible.append((metrics["awake_false_positive_rate"], -threshold, metrics))
    _, negative_threshold, metrics = min(feasible, key=lambda entry: entry[:2])
    return -negative_threshold, metrics


def evaluate_rows(
    estimator: Pipeline, threshold: float, rows: TrainingRows
) -> dict[str, Any]:
    scores = predict_scores(estimator, rows.features)
    predicted = [score >= threshold for score in scores]
    return {
        "metrics": calculate_metrics(rows.labels, predicted),
        "baseline": calculate_metrics(rows.labels, rows.baseline),
        "coverage": len(rows.labels) / rows.eligible_windows
        if rows.eligible_windows
        else 0,
        "by_posture": {
            posture: calculate_metrics(
                [
                    label
                    for label, name in zip(rows.labels, rows.postures, strict=True)
                    if name == posture
                ],
                [
                    value
                    for value, name in zip(predicted, rows.postures, strict=True)
                    if name == posture
                ],
            )
            for posture in sorted(set(rows.postures))
        },
    }


def train_model(
    details: list[RecordingDetail],
    model_id: str,
    directory: Path,
    presence_mm: int = 300,
) -> dict[str, Any]:
    development = [item for item in details if item.recording.role == "development"]
    held_out = [item for item in details if item.recording.role == "held_out"]
    rows = build_rows(development, presence_mm)
    groups = sorted(set(rows.groups))
    if len(groups) < 3:
        raise ValueError(
            "Need three development recordings with valid labelled windows"
        )
    if any(
        {
            label
            for label, group in zip(rows.labels, rows.groups, strict=True)
            if group == current
        }
        != {0, 1}
        for current in groups
    ):
        raise ValueError(
            "Each development recording needs both awake and drowsy windows"
        )
    candidates: dict[str, Any] = {}
    for name in ("decision_tree", "random_forest"):
        scores = [0.0] * len(rows.labels)
        for group in groups:
            train_indices = [
                index for index, value in enumerate(rows.groups) if value != group
            ]
            test_indices = [
                index for index, value in enumerate(rows.groups) if value == group
            ]
            estimator = create_estimator(name)
            fit_estimator(estimator, rows, train_indices)
            predictions = predict_scores(
                estimator, [rows.features[index] for index in test_indices]
            )
            for index, score in zip(test_indices, predictions, strict=True):
                scores[index] = score
        threshold, metrics = tune_threshold(rows.labels, scores)
        candidates[name] = {"threshold": threshold, "metrics": metrics}
    selected = min(
        candidates,
        key=lambda name: candidates[name]["metrics"]["awake_false_positive_rate"],
    )
    threshold = float(candidates[selected]["threshold"])
    estimator = create_estimator(selected)
    fit_estimator(estimator, rows, list(range(len(rows.labels))))
    snapshot = json.dumps([detail.model_dump() for detail in details], sort_keys=True)
    dataset_id = hashlib.sha256(snapshot.encode()).hexdigest()
    artifact = {
        "feature_version": FEATURE_VERSION,
        "presence_mm": presence_mm,
        "estimator": estimator,
        "threshold": threshold,
        "dataset_id": dataset_id,
        "sklearn_version": sklearn.__version__,
        "python_version": platform.python_version(),
    }
    directory.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, directory / f"{model_id}.joblib")
    return {
        "model_id": model_id,
        "selected": selected,
        "threshold": threshold,
        "dataset_id": dataset_id,
        "feature_version": FEATURE_VERSION,
        "sklearn_version": sklearn.__version__,
        "python_version": platform.python_version(),
        "validation": candidates,
        "validation_groups": groups,
        "baseline": calculate_metrics(rows.labels, rows.baseline),
        "always_positive": calculate_metrics(rows.labels, [True] * len(rows.labels)),
        "coverage": len(rows.labels) / rows.eligible_windows
        if rows.eligible_windows
        else 0,
        "weak_separation": candidates[selected]["metrics"]["awake_false_positive_rate"]
        >= 0.8,
        "held_out": evaluate_rows(
            estimator, threshold, build_rows(held_out, presence_mm)
        )
        if held_out
        else None,
        "provenance": "staged_posture",
    }


def load_artifact(
    directory: Path, model_id: str, presence_mm: int | None = None
) -> dict[str, Any]:
    if len(model_id) != 32 or any(
        character not in "0123456789abcdef" for character in model_id
    ):
        raise ValueError("Invalid model identifier")
    artifact: dict[str, Any] = joblib.load(directory / f"{model_id}.joblib")
    if (
        artifact["feature_version"] != FEATURE_VERSION
        or artifact["sklearn_version"] != sklearn.__version__
        or (presence_mm is not None and artifact.get("presence_mm") != presence_mm)
    ):
        raise ValueError(
            "Model feature/library version mismatch; retrain with this installation"
        )
    return artifact
