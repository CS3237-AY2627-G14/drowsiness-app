from pathlib import Path
from typing import Any

import joblib
import sklearn
from sklearn.pipeline import Pipeline

from modules.processing.sensor_features import FEATURE_VERSION


def predict_scores(estimator: Pipeline, features: list[list[float]]) -> list[float]:
    if not features:
        return []
    scores: list[float] = estimator.predict_proba(features)[:, 1].tolist()
    return scores


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
