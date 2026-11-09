import { z } from 'zod'

const optionalId = z.coerce
  .number()
  .int()
  .positive()
  .optional()
  .catch(undefined)
export const publishSearchSchema = z.object({
  room: optionalId,
  seat: z
    .string()
    .regex(/^[A-Za-z0-9]+$/)
    .optional()
    .catch(undefined),
})
