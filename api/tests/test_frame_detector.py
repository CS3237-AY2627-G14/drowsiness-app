import math
from io import BytesIO
from unittest.mock import Mock
from uuid import uuid4

import numpy as np
import pytest
import torch
from numpy.typing import NDArray
from PIL import Image
from torch import nn

from core.config import Settings
from modules.processing.inference import frame_detector
from modules.processing.schemas import FrameInput, QueuedFrame


class RecordingClassifier(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.batches: list[torch.Tensor] = []

    def forward(self, batch: torch.Tensor) -> torch.Tensor:
        self.batches.append(batch.clone())
        return torch.cat((torch.zeros_like(batch), batch / 255.0), dim=1)


def encode_frame_jpeg(value: int) -> bytes:
    image = Image.new("RGB", (8, 8), (value, value, value))
    output = BytesIO()
    image.save(output, format="JPEG")
    return output.getvalue()


def transform_face(image: Image.Image) -> torch.Tensor:
    pixels = np.asarray(image)
    return torch.tensor([float(pixels[0, 0, 0])])


def measure_eyes(
    mesh: object, rgb: NDArray[np.uint8]
) -> tuple[float | None, float | None]:
    return (0.1, 0.2) if rgb[0, 0, 0] else (None, None)


def crop_face(face_detector: object, rgb: NDArray[np.uint8]) -> Image.Image | None:
    return Image.fromarray(rgb) if rgb[0, 0, 0] else None


@pytest.fixture
def classifier(monkeypatch: pytest.MonkeyPatch) -> RecordingClassifier:
    model = RecordingClassifier()
    resources = frame_detector.DetectorResources(
        model=model,
        transform=transform_face,
        mesh=None,
        face_detector=None,
        device=torch.device("cpu"),
        fatigue_index=1,
        settings=Settings(),
    )
    monkeypatch.setattr(frame_detector, "_resources", resources)
    monkeypatch.setattr(frame_detector, "measure_eye_openness", measure_eyes)
    monkeypatch.setattr(frame_detector, "detect_face_crop", crop_face)
    monkeypatch.setattr(frame_detector, "monotonic", Mock(side_effect=[1.0, 1.25]))
    return model


@pytest.mark.parametrize("values", [(32, None, 0, 192), (0, None), ()])
def test_batch_preserves_frame_order_and_classifies_only_faces_together(
    classifier: RecordingClassifier, values: tuple[int | None, ...]
) -> None:
    queued_frames: list[QueuedFrame] = []
    for index, value in enumerate(values):
        jpeg = b"invalid" if value is None else encode_frame_jpeg(value)
        frame = FrameInput(frame_id=index + 1, captured_at_ms=float(index), jpeg=jpeg)
        queued_frame = QueuedFrame(connection_id=uuid4(), received_at=0.0, frame=frame)
        queued_frames.append(queued_frame)

    results = frame_detector.predict_batch(tuple(queued_frames))

    assert len(results) == len(queued_frames)
    for result, work, value in zip(results, queued_frames, values, strict=True):
        assert result.connection_id == work.connection_id
        assert result.frame_id == work.frame.frame_id
        assert result.captured_at_ms == work.frame.captured_at_ms
        assert result.processing_ms == 250.0
        assert result.error == ("invalid_frame" if value is None else None)
        if value is None or value == 0:
            assert result.fatigue_probability is None
            assert result.left_ear is None and result.right_ear is None
        else:
            expected_probability = 1 / (1 + math.exp(-value / 255.0))
            assert result.fatigue_probability == pytest.approx(expected_probability)
            assert result.left_ear == 0.1 and result.right_ear == 0.2

    face_values = [value for value in values if value is not None and value > 0]
    assert len(classifier.batches) == (1 if face_values else 0)
    if face_values:
        assert classifier.batches[0].tolist() == [[value] for value in face_values]
