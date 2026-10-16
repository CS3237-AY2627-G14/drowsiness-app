import asyncio
from io import BytesIO
from pathlib import Path
from typing import Literal
from uuid import uuid4

import pytest
from PIL import Image, ImageOps

from core.config import Settings
from modules.processing.inference import create_inference_runtime
from modules.processing.schemas import FrameInput, QueuedFrame


def encode_portrait_jpeg() -> bytes:
    portrait_path = Path(__file__).parent / "fixtures" / "portrait.jpg"
    with Image.open(portrait_path) as image:
        rgb_image = image.convert("RGB")
        padded = ImageOps.pad(
            rgb_image,
            (1280, 720),
            color=(16, 29, 34),
            method=Image.Resampling.BILINEAR,
        )
        output = BytesIO()
        padded.save(output, format="JPEG", quality=80)
        return output.getvalue()


@pytest.mark.inference
@pytest.mark.parametrize("device", ["cpu", "mps", "cuda"])
def test_real_combined_detector_and_camera_isolation(
    device: Literal["cpu", "mps", "cuda"],
) -> None:
    import torch

    if device == "mps" and not torch.backends.mps.is_available():
        pytest.skip("MPS hardware is unavailable")
    if device == "cuda" and not torch.cuda.is_available():
        pytest.skip("CUDA hardware is unavailable")

    async def run() -> None:
        settings = Settings(inference_device=device, inference_workers=1)
        async with create_inference_runtime(settings) as runtime:
            a, b = uuid4(), uuid4()
            portrait = encode_portrait_jpeg()
            blank = BytesIO()
            blank_image = Image.new("RGB", (1280, 720))
            blank_image.save(blank, format="JPEG")
            blank_jpeg = blank.getvalue()
            camera_frames = (
                (a, portrait),
                (b, blank_jpeg),
                (a, portrait),
                (b, b"invalid"),
            )
            queued_frames: list[QueuedFrame] = []
            for index, (connection_id, jpeg) in enumerate(camera_frames):
                frame = FrameInput(
                    frame_id=index + 1, captured_at_ms=float(index * 200), jpeg=jpeg
                )
                queued_frame = QueuedFrame(
                    connection_id=connection_id, received_at=0.0, frame=frame
                )
                queued_frames.append(queued_frame)
            batch = tuple(queued_frames)
            results = await runtime.frame_predictor.predict_batch(batch)
            first, no_face, repeated, invalid = results
            assert first.error is None and first.fatigue_probability is not None
            assert first.left_ear is not None and first.right_ear is not None
            assert 0 <= first.fatigue_probability <= 1
            assert no_face.fatigue_probability is None and no_face.left_ear is None
            assert repeated.left_ear == pytest.approx(first.left_ear, abs=1e-6)
            assert repeated.fatigue_probability == pytest.approx(
                first.fatigue_probability, abs=1e-5
            )
            assert invalid.error == "invalid_frame"
            oversized = BytesIO()
            oversized_image = Image.new("RGB", (1281, 720))
            oversized_image.save(oversized, format="JPEG")
            oversized_jpeg = oversized.getvalue()
            oversized_frame = FrameInput(
                frame_id=5, captured_at_ms=1000.0, jpeg=oversized_jpeg
            )
            oversized_work = batch[0].model_copy(update={"frame": oversized_frame})
            rejected = await runtime.frame_predictor.predict_batch((oversized_work,))
            assert rejected[0].error == "invalid_frame"

    asyncio.run(run())


@pytest.mark.parametrize(
    ("metadata", "message"),
    [
        ({}, "Unsupported checkpoint model_name"),
        ({"model_name": "unknown"}, "Unsupported checkpoint model_name"),
        ({"class_to_idx": {"active": 1, "fatigue": 0}}, "valid indices"),
    ],
)
def test_invalid_checkpoint_metadata_fails(
    tmp_path: Path, metadata: dict[str, object], message: str
) -> None:
    import torch

    from modules.processing.inference.frame_detector import load_classifier

    path = tmp_path / "invalid.pth"
    torch.save(
        {
            "classes": ["active", "fatigue"],
            "class_to_idx": {"active": 0, "fatigue": 1},
            **metadata,
        },
        path,
    )
    with pytest.raises(ValueError, match=message):
        load_classifier(path)


@pytest.mark.inference
def test_v4_uses_checkpoint_preprocessing(tmp_path: Path) -> None:
    import torch

    from modules.processing.inference.frame_detector import load_classifier

    checkpoint = torch.load(
        "models/drowsiness_mobilenetv4_20261016_013212.pth",
        map_location="cpu",
        weights_only=True,
    )
    checkpoint["data_config"].update(
        input_size=(3, 160, 160), mean=(0.5, 0.5, 0.5), std=(0.5, 0.5, 0.5)
    )
    path = tmp_path / "custom_preprocessing.pth"
    torch.save(checkpoint, path)
    _, transform, fatigue_index = load_classifier(path)
    image = Image.new("RGB", (320, 240))
    tensor = transform(image)
    assert tensor.shape == (3, 160, 160)
    assert torch.all(tensor == -1)
    assert fatigue_index == 1


@pytest.mark.inference
def test_missing_checkpoint_fails_startup(tmp_path: Path) -> None:
    async def run() -> None:
        with pytest.raises(RuntimeError, match="checkpoint is missing"):
            settings = Settings(model_path=tmp_path / "absent.pth")
            async with create_inference_runtime(settings):
                pass

    asyncio.run(run())
