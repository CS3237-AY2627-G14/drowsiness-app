from collections import deque
from statistics import median

import numpy as np

from modules.processing.calibration.schemas import StoredSample

FEATURE_VERSION = 1
SENSORS = ("upper_cm", "lower_mm", "back_adc", "desk_adc")


def extract_features(samples: list[StoredSample]) -> list[float] | None:
    if len(samples) < 8 or samples[-1].received_at - samples[0].received_at < 1.4:
        return None
    if len({sample.telemetry.boot_id for sample in samples}) != 1:
        return None
    if any(
        current.received_at - previous.received_at > 0.6
        for previous, current in zip(samples, samples[1:], strict=False)
    ):
        return None
    features: list[float] = []
    for sensor in SENSORS:
        values = [
            value
            for sample in samples
            if (value := getattr(sample.telemetry, sensor)) is not None
        ]
        if sensor != "upper_cm" and len(values) != len(samples):
            return None
        features.extend(
            [
                float(median(values)) if values else float("nan"),
                float(np.percentile(values, 75) - np.percentile(values, 25))
                if values
                else float("nan"),
                float(values[-1] - values[0]) if values else float("nan"),
                len(values) / len(samples),
            ]
        )
    return features


def baseline_result(sample: StoredSample, presence_mm: int = 300) -> bool | None:
    reading = sample.telemetry
    if reading.lower_mm is None or reading.lower_mm >= presence_mm:
        return None
    if reading.upper_cm is None or reading.desk_adc < 1000:
        return None
    if reading.desk_adc <= 2000 and reading.back_adc == 0:
        return True
    return reading.upper_cm >= 6


class SensorWindow:
    def __init__(self) -> None:
        self.samples: deque[StoredSample] = deque()

    def clear(self) -> None:
        self.samples.clear()

    def add(self, sample: StoredSample) -> None:
        if self.samples:
            previous = self.samples[-1]
            if (
                previous.telemetry.boot_id != sample.telemetry.boot_id
                or sample.received_at - previous.received_at > 0.6
            ):
                self.clear()
        self.samples.append(sample)
        while self.samples and self.samples[0].received_at <= sample.received_at - 2:
            self.samples.popleft()

    def features(self) -> list[float] | None:
        return extract_features(list(self.samples))
