from pydantic import BaseModel, ConfigDict, PositiveInt


class RoomInfo(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    id: PositiveInt
    name: str


class SeatInfo(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    id: PositiveInt
    room_id: PositiveInt
    seat_number: PositiveInt


class ClassroomInfo(RoomInfo):
    seats: list[SeatInfo]
