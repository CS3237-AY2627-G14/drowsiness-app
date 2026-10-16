import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from time import monotonic
from typing import Any

import numpy as np
import timm
import torch
import torch.nn as nn
from numpy.typing import NDArray
from PIL import Image
from timm.data.transforms_factory import create_transform

from core.config import Settings
from modules.processing.schemas import FrameMeasurements, QueuedFrame

LEFT_EYE = (33, 160, 158, 133, 153, 144)
RIGHT_EYE = (362, 385, 387, 263, 373, 380)


@dataclass(frozen=True)
class DetectorResources:
    model: nn.Module
    transform: Callable[[Image.Image], torch.Tensor]
    mesh: Any
    face_detector: Any
    device: torch.device
    fatigue_index: int
    settings: Settings


_resources: DetectorResources | None = None


def load_classifier(
    path: Path,
) -> tuple[nn.Module, Callable[[Image.Image], torch.Tensor], int]:
    checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    classes = checkpoint["classes"]
    class_to_idx = checkpoint["class_to_idx"]
    if (
        len(classes) != 2
        or set(classes) != {"active", "fatigue"}
        or class_to_idx != {label: index for index, label in enumerate(classes)}
    ):
        raise ValueError(
            "Checkpoint must classify active and fatigue with valid indices"
        )
    model_name = checkpoint.get("model_name")
    if model_name != "mobilenetv4_conv_small.e2400_r224_in1k":
        raise ValueError(f"Unsupported checkpoint model_name: {model_name}")
    model = timm.create_model(model_name, pretrained=False, num_classes=2)
    transform = create_transform(**checkpoint["data_config"], is_training=False)
    model.load_state_dict(checkpoint["model_state_dict"])
    return model, transform, int(class_to_idx["fatigue"])


def select_device(requested: str) -> str:
    available = {
        "cpu": True,
        "cuda": torch.cuda.is_available(),
        "mps": torch.backends.mps.is_available(),
    }
    if requested == "auto":
        return next(device for device in ("cuda", "mps", "cpu") if available[device])
    if not available[requested]:
        raise RuntimeError(f"Requested inference device is unavailable: {requested}")
    return requested


def initialize_detector(settings: Settings, device: str) -> None:
    import mediapipe as mp

    global _resources
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    model, transform, fatigue_index = load_classifier(settings.model_path)
    model.to(device)
    model.eval()
    mesh = mp.solutions.face_mesh.FaceMesh(
        static_image_mode=True,
        max_num_faces=1,
        refine_landmarks=False,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    face_detector = mp.solutions.face_detection.FaceDetection(
        model_selection=0, min_detection_confidence=0.5
    )
    torch_device = torch.device(device)
    _resources = DetectorResources(
        model,
        transform,
        mesh,
        face_detector,
        torch_device,
        fatigue_index,
        settings,
    )
    warm_up_classifier(_resources)


def close_detector() -> None:
    global _resources
    if _resources is not None:
        _resources.mesh.close()
        _resources.face_detector.close()
        _resources = None


def warm_up_classifier(resources: DetectorResources) -> None:
    with torch.inference_mode():
        image = Image.new("RGB", (224, 224))
        tensor = resources.transform(image)
        batch = tensor.unsqueeze(0)
        device_batch = batch.to(resources.device)
        resources.model(device_batch)


def decode_frame_image(jpeg: bytes, settings: Settings) -> NDArray[np.uint8]:
    image_buffer = BytesIO(jpeg)
    with Image.open(image_buffer) as image:
        width, height = image.size
        if (
            image.format != "JPEG"
            or not 0 < width <= settings.frame_width
            or not 0 < height <= settings.frame_height
        ):
            raise ValueError("Invalid frame dimensions or format")
        rgb_image = image.convert("RGB")
        return np.asarray(rgb_image)


def measure_eye_openness(
    mesh: Any, rgb: NDArray[np.uint8]
) -> tuple[float | None, float | None]:
    mesh_result = mesh.process(rgb)
    if not mesh_result.multi_face_landmarks:
        return None, None
    height, width = rgb.shape[:2]
    landmarks = mesh_result.multi_face_landmarks[0].landmark
    ears: list[float | None] = []
    for indices in (LEFT_EYE, RIGHT_EYE):
        points = [
            (float(landmarks[index].x) * width, float(landmarks[index].y) * height)
            for index in indices
        ]
        ear = calculate_eye_aspect_ratio(points)
        ears.append(ear)
    return ears[0], ears[1]


def detect_face_crop(face_detector: Any, rgb: NDArray[np.uint8]) -> Image.Image | None:
    face_result = face_detector.process(rgb)
    if not face_result.detections:
        return None
    detection = max(
        face_result.detections,
        key=lambda face: (
            face.location_data.relative_bounding_box.width
            * face.location_data.relative_bounding_box.height
        ),
    )
    height, width = rgb.shape[:2]
    box = detection.location_data.relative_bounding_box
    x1 = max(0, int(box.xmin * width))
    y1 = max(0, int(box.ymin * height))
    x2 = min(width, int((box.xmin + box.width) * width))
    y2 = min(height, int((box.ymin + box.height) * height))
    if x2 <= x1 or y2 <= y1:
        return None
    face_pixels = rgb[y1:y2, x1:x2]
    return Image.fromarray(face_pixels)


def predict_fatigue_probabilities(
    resources: DetectorResources, faces: list[torch.Tensor]
) -> list[float]:
    with torch.inference_mode():
        batch = torch.stack(faces)
        device_batch = batch.to(resources.device)
        logits = resources.model(device_batch)
        class_probabilities = torch.softmax(logits, dim=1)
        fatigue_probabilities = class_probabilities[:, resources.fatigue_index]
        cpu_probabilities = fatigue_probabilities.cpu()
        probabilities: list[float] = cpu_probabilities.tolist()
    return probabilities


def predict_batch(batch: tuple[QueuedFrame, ...]) -> tuple[FrameMeasurements, ...]:
    resources = _resources
    assert resources is not None
    started_at = monotonic()
    batch_measurements: list[FrameMeasurements] = []
    faces: list[torch.Tensor] = []
    face_indices: list[int] = []
    for work in batch:
        measurements = FrameMeasurements(
            connection_id=work.connection_id,
            frame_id=work.frame.frame_id,
            captured_at_ms=work.frame.captured_at_ms,
        )
        try:
            rgb = decode_frame_image(work.frame.jpeg, resources.settings)
        except (OSError, ValueError, Image.DecompressionBombError):
            invalid_measurements = measurements.model_copy(
                update={"error": "invalid_frame"}
            )
            batch_measurements.append(invalid_measurements)
            continue
        left_ear, right_ear = measure_eye_openness(resources.mesh, rgb)
        measurements = measurements.model_copy(
            update={"left_ear": left_ear, "right_ear": right_ear}
        )
        face_crop = detect_face_crop(resources.face_detector, rgb)
        if face_crop is not None:
            face_tensor = resources.transform(face_crop)
            faces.append(face_tensor)
            face_indices.append(len(batch_measurements))
        batch_measurements.append(measurements)
    if faces:
        probabilities = predict_fatigue_probabilities(resources, faces)
        for index, probability in zip(face_indices, probabilities, strict=True):
            batch_measurements[index] = batch_measurements[index].model_copy(
                update={"fatigue_probability": float(probability)}
            )
    elapsed_ms = (monotonic() - started_at) * 1000
    return tuple(
        measurements.model_copy(update={"processing_ms": elapsed_ms})
        for measurements in batch_measurements
    )


def calculate_eye_aspect_ratio(points: Sequence[tuple[float, float]]) -> float | None:
    horizontal_distance = math.dist(points[0], points[3])
    if horizontal_distance == 0:
        return None
    upper_vertical_distance = math.dist(points[1], points[5])
    lower_vertical_distance = math.dist(points[2], points[4])
    return (upper_vertical_distance + lower_vertical_distance) / (
        2 * horizontal_distance
    )
