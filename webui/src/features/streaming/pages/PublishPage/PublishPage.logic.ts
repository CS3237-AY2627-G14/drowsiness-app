import { getDemoPublishToken } from './utils/getDemoPublishToken'
import type { Classroom, Seat } from '#/types/classrooms'
import type {
  PublishSelection,
  PublishTokenOverride,
} from './PublishPage.types'

export const resolvePublishSelection = (
  classrooms: Classroom[],
  roomId: number | undefined,
  seatId: number | undefined,
): PublishSelection => {
  const room =
    classrooms.find((candidate) => candidate.id === roomId) ?? classrooms[0]
  const seat =
    room?.seats.find((candidate) => candidate.id === seatId) ?? room?.seats[0]
  return { room, seat }
}

export const resolvePublishToken = (
  seat: Seat | undefined,
  override: PublishTokenOverride | null,
): string => {
  if (!seat) return ''
  if (override?.seatId === seat.id) return override.token
  return getDemoPublishToken(seat)
}
