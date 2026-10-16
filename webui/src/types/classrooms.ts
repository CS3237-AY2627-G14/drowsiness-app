export type Seat = {
  id: number
  room_id: number
  seat_number: number
}

export type Classroom = {
  id: number
  name: string
  seats: Seat[]
}
