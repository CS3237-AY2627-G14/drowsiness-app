from typing import Protocol

from modules.processing.schemas import FrameMeasurements, QueuedFrame


class FramePredictor(Protocol):
    async def predict_batch(
        self, batch: tuple[QueuedFrame, ...]
    ) -> tuple[FrameMeasurements, ...]: ...
