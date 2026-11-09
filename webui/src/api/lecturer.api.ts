import { axiosClient } from '#/lib/axiosClient.ts'

export type LecturerSeatStatus = {
  seat_id: number
  drowsy: boolean
}

export type LecturerSeatSnapshot = {
  drowsy_seats: number[]
  seats: LecturerSeatStatus[]
}

export const getLecturerSeats = async (
  signal: AbortSignal,
): Promise<LecturerSeatSnapshot> => {
  const response = await axiosClient.get<LecturerSeatSnapshot>(
    '/api/lecturer/seats',
    { signal },
  )
  return response.data
}
