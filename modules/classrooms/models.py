from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base


class RoomModel(Base):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    seats: Mapped[list[SeatModel]] = relationship(back_populates="room")


class SeatModel(Base):
    __tablename__ = "seats"
    __table_args__ = (
        UniqueConstraint("room_id", "seat_number", name="uq_seats_room_number"),
        CheckConstraint("seat_number > 0", name="ck_seats_positive_number"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"))
    seat_number: Mapped[int]
    room: Mapped[RoomModel] = relationship(back_populates="seats")
