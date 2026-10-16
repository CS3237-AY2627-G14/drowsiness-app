import asyncio
import logging
import multiprocessing
import os
import signal
from collections.abc import AsyncIterator
from concurrent.futures import ProcessPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass
from multiprocessing.synchronize import Barrier
from multiprocessing.util import Finalize

from core.config import Settings
from modules.processing.inference.frame_predictor import FramePredictor
from modules.processing.schemas import FrameMeasurements, QueuedFrame


@dataclass(frozen=True)
class InferenceRuntime:
    frame_predictor: FramePredictor
    workers: int


class ProcessPoolFramePredictor:
    def __init__(self, process_pool: ProcessPoolExecutor) -> None:
        self._process_pool = process_pool

    async def predict_batch(
        self, batch: tuple[QueuedFrame, ...]
    ) -> tuple[FrameMeasurements, ...]:
        from modules.processing.inference.frame_detector import predict_batch

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._process_pool, predict_batch, batch)


def initialize_process(settings: Settings, device: str, barrier: Barrier) -> None:
    from modules.processing.inference.frame_detector import (
        close_detector,
        initialize_detector,
    )

    signal.signal(signal.SIGINT, signal.SIG_IGN)
    initialize_detector(settings, device)
    Finalize(None, close_detector, exitpriority=10)
    barrier.wait(timeout=60)


def get_worker_pid() -> int:
    return os.getpid()


@asynccontextmanager
async def create_inference_runtime(
    settings: Settings,
) -> AsyncIterator[InferenceRuntime]:
    from modules.processing.inference.frame_detector import select_device

    if not settings.model_path.is_file():
        raise RuntimeError(
            "CNN checkpoint is missing. Place the checkpoint at DROWSINESS_MODEL_PATH; "
            "see models/README.md for provisioning instructions."
        )
    device = select_device(settings.inference_device)
    workers = settings.inference_workers or (2 if device == "cpu" else 1)
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(workers)
    pool = ProcessPoolExecutor(
        max_workers=workers,
        mp_context=context,
        initializer=initialize_process,
        initargs=(settings, device, barrier),
    )
    loop = asyncio.get_running_loop()

    try:
        readiness_checks = [
            loop.run_in_executor(pool, get_worker_pid) for _ in range(workers)
        ]
        await asyncio.gather(*readiness_checks)
        logger = logging.getLogger(__name__)
        logger.info("Inference ready device=%s workers=%d", device, workers)
        frame_predictor = ProcessPoolFramePredictor(pool)
        yield InferenceRuntime(frame_predictor, workers)
    finally:
        await asyncio.to_thread(pool.shutdown, wait=True, cancel_futures=True)
