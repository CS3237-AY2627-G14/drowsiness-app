import { useQuery } from '@tanstack/react-query'
import { getClassrooms } from '#/api/getClassrooms.api.ts'

export const useClassrooms = () => {
  return useQuery({
    queryKey: ['classrooms'],
    queryFn: ({ signal }) => getClassrooms(signal),
  })
}
