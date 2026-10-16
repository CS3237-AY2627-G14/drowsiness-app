import type { SeatSelectorProps } from '../PublishPage.types'
import type { ChangeEvent } from 'react'

export const SeatSelector = ({
  classrooms,
  room,
  seatId,
  disabled,
  onRoomChange,
  onSeatChange,
}: SeatSelectorProps) => {
  const hasSeats = room.seats.length > 0
  const selectedSeatId = seatId ?? ''
  const handleRoomChange = (event: ChangeEvent<HTMLSelectElement>) => {
    const roomId = Number(event.currentTarget.value)
    onRoomChange(roomId)
  }
  const handleSeatChange = (event: ChangeEvent<HTMLSelectElement>) => {
    const selectedId = Number(event.currentTarget.value)
    onSeatChange(selectedId)
  }
  return (
    <fieldset disabled={disabled} className="grid gap-4 disabled:opacity-60">
      <legend className="mb-4 font-semibold">Your seat</legend>
      <div className="grid gap-1.5">
        <label htmlFor="room" className="text-sm font-medium">
          Room
        </label>
        <select
          id="room"
          value={room.id}
          onChange={handleRoomChange}
          className="form-control"
        >
          {classrooms.map((value) => (
            <option key={value.id} value={value.id}>
              {value.name}
            </option>
          ))}
        </select>
      </div>
      <div className="grid gap-1.5">
        <label htmlFor="seat" className="text-sm font-medium">
          Seat
        </label>
        <select
          id="seat"
          value={selectedSeatId}
          disabled={!hasSeats}
          onChange={handleSeatChange}
          className="form-control"
        >
          {!hasSeats ? <option value="">No seats available</option> : null}
          {room.seats.map((seat) => (
            <option key={seat.id} value={seat.id}>
              Seat {seat.seat_number}
            </option>
          ))}
        </select>
      </div>
    </fieldset>
  )
}
