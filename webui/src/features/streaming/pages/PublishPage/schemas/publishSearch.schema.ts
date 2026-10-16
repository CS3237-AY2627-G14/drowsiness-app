import { z } from 'zod'

const optionalId = z.coerce
  .number()
  .int()
  .positive()
  .optional()
  .catch(undefined)
export const publishSearchSchema = z.object({
  room: optionalId,
  seat: optionalId,
})
