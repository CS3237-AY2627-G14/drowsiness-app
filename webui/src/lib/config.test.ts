import { afterEach, expect, it, vi } from 'vitest'

afterEach(() => {
  vi.unstubAllEnvs()
  vi.resetModules()
})

it('defaults capture to one frame per second', async () => {
  vi.stubEnv('VITE_VIDEO_FPS', undefined)
  vi.resetModules()
  const { videoConfig } = await import('./config')
  expect(videoConfig.frameRate).toBe(1)
})

it('allows configuring capture at 10 FPS', async () => {
  vi.stubEnv('VITE_VIDEO_FPS', '10')
  vi.resetModules()
  const { videoConfig } = await import('./config')
  expect(videoConfig.frameRate).toBe(10)
})
