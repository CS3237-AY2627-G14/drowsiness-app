import { publishSearchSchema } from '../schemas/publishSearch.schema'

export const validatePublishSearch = (search: Record<string, unknown>) =>
  publishSearchSchema.parse(search)
