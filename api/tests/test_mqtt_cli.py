import sys

import pytest

from tests.test_publish_mqtt_test_data import parse_arguments


@pytest.mark.parametrize("seat_id", ["1", "001", "1e3", "true", "A1"])
def test_sensor_cli_preserves_string_seat_ids(
    monkeypatch: pytest.MonkeyPatch, seat_id: str
) -> None:
    monkeypatch.setattr(sys, "argv", ["sensor-cli", "--student", seat_id])
    assert parse_arguments().student == seat_id


@pytest.mark.parametrize("seat_id", ["", "A/1", "A-1", "Ａ1"])
def test_sensor_cli_rejects_invalid_seat_ids(
    monkeypatch: pytest.MonkeyPatch, seat_id: str
) -> None:
    monkeypatch.setattr(sys, "argv", ["sensor-cli", "--student", seat_id])
    with pytest.raises(SystemExit) as error:
        parse_arguments()
    assert error.value.code == 2
