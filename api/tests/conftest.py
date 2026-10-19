from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from core.config import Settings
from main import create_app
from tests.helpers import MutableClock, fake_inference_runtime


@pytest.fixture
def clock() -> MutableClock:
    return MutableClock()


@pytest.fixture
def client(clock: MutableClock) -> Iterator[TestClient]:
    settings = Settings(demo_seat_count=10, mqtt_enabled=False)
    application = create_app(
        settings,
        clock=clock,
        inference_factory=fake_inference_runtime,
    )
    with TestClient(application) as test_client:
        yield test_client
