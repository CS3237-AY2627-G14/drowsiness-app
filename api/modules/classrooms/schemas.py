from pydantic import BaseModel, ConfigDict, Field, PositiveInt


class RoomInfo(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    id: PositiveInt
    name: str


class SeatInfo(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    id: str = Field(pattern=r"^[A-Za-z0-9]+$")
    room_id: PositiveInt
    seat_number: PositiveInt


class ClassroomInfo(RoomInfo):
    seats: list[SeatInfo]
