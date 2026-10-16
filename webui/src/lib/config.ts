import { z } from 'zod'

const configSchema = z.object({
  width: z.coerce.number().int().positive().default(1280),
  height: z.coerce.number().int().positive().default(720),
  frameRate: z.coerce.number().positive().default(1),
  jpegQuality: z.coerce.number().min(0).max(1).default(0.8),
})

export const videoConfig = Object.freeze(
  configSchema.parse({
    width: import.meta.env.VITE_VIDEO_WIDTH,
    height: import.meta.env.VITE_VIDEO_HEIGHT,
    frameRate: import.meta.env.VITE_VIDEO_FPS,
    jpegQuality: import.meta.env.VITE_JPEG_QUALITY,
  }),
)
