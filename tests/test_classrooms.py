from fastapi.testclient import TestClient


def test_classroom_topology_is_available_without_credentials(
    client: TestClient,
) -> None:
    response = client.get("/api/classrooms")
    assert response.status_code == 200
    assert response.json() == [
        {
            "id": 101,
            "name": "Room 101",
            "seats": [
                {"id": number, "room_id": 101, "seat_number": number}
                for number in range(1, 11)
            ],
        }
    ]
    assert "token" not in response.text
