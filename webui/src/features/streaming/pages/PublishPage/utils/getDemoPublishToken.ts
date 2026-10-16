import type { Seat } from '#/types/classrooms'

export const getDemoPublishToken = (seat: Seat): string => {
  return `demo-room-${seat.room_id}-seat-${seat.seat_number}`
}
