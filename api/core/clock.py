from datetime import UTC, datetime
from time import monotonic
from typing import Protocol


class Clock(Protocol):
    """Provide UTC-aware wall-clock time."""

    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class Timer(Protocol):
    """Provide monotonic time in seconds for measuring elapsed duration."""

    def now(self) -> float: ...


class MonotonicTimer:
    def now(self) -> float:
        return monotonic()


def utc_now() -> datetime:
    return datetime.now(UTC)
