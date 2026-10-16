import { axiosClient } from '#/lib/axiosClient.ts'
import type { Classroom } from '#/types/classrooms'

export const getClassrooms = async (
  signal: AbortSignal,
): Promise<Classroom[]> => {
  const response = await axiosClient.get<Classroom[]>('/api/classrooms', {
    signal,
  })
  return response.data
}
