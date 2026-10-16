import { afterEach, expect, it, vi } from 'vitest'
import { streamFrames } from './streamFrames'
import type { CapturedFrame } from './types/camera.types'

afterEach(() => {
  vi.useRealTimers()
})

it('skips capture when upload capacity is unavailable', async () => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'performance'] })
  const controller = new AbortController()
  const captureFrame = vi.fn(async () => ({
    capturedAtMs: 0,
    jpeg: new Blob(['jpeg']),
  }))
  const connection = {
    canSendFrame: () => false,
    sendFrame: vi.fn(() => true),
    close: async () => {},
  }
  const stopped = streamFrames({
    captureFrame,
    connection,
    signal: controller.signal,
  })
  await vi.advanceTimersByTimeAsync(1000)
  controller.abort()
  await stopped
  expect(captureFrame).not.toHaveBeenCalled()
  expect(connection.sendFrame).not.toHaveBeenCalled()
})

it('never overlaps encoding and discards an encoding completed after cancellation', async () => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'performance'] })
  const controller = new AbortController()
  let finishEncoding: (frame: CapturedFrame) => void = () => {}
  const captureFrame = vi.fn(
    () =>
      new Promise<CapturedFrame>((resolve) => {
        finishEncoding = resolve
      }),
  )
  const connection = {
    canSendFrame: () => true,
    sendFrame: vi.fn(() => true),
    close: async () => {},
  }
  const stopped = streamFrames({
    captureFrame,
    connection,
    signal: controller.signal,
  })
  await vi.advanceTimersByTimeAsync(1000)
  expect(captureFrame).toHaveBeenCalledTimes(1)
  controller.abort()
  finishEncoding({ capturedAtMs: 0, jpeg: new Blob(['jpeg']) })
  await stopped
  expect(connection.sendFrame).not.toHaveBeenCalled()
})

it('sends near ten FPS without awaiting inference results', async () => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'performance'] })
  const controller = new AbortController()
  const captureFrame = async () => ({
    capturedAtMs: performance.now(),
    jpeg: new Blob(['jpeg']),
  })
  const connection = {
    canSendFrame: () => true,
    sendFrame: vi.fn(() => true),
    close: async () => {},
  }
  const stopped = streamFrames({
    captureFrame,
    connection,
    signal: controller.signal,
  })
  await vi.advanceTimersByTimeAsync(999)
  controller.abort()
  await stopped
  expect(connection.sendFrame).toHaveBeenCalledTimes(10)
})
