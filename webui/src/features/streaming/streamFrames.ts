import { videoConfig } from '#/lib/config'
import { waitForNextFrame } from './utils/timing'
import type { StreamFramesOptions } from './types/frameStream.types'

export const streamFrames = async ({
  captureFrame,
  connection,
  signal,
}: StreamFramesOptions): Promise<void> => {
  const intervalMs = 1000 / videoConfig.frameRate
  while (!signal.aborted) {
    const startedAt = performance.now()
    if (connection.canSendFrame()) {
      const frame = await captureFrame()
      // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition -- Cancellation can change during encoding.
      if (signal.aborted) return
      if (frame) connection.sendFrame(frame)
    }
    const elapsedMs = performance.now() - startedAt
    const remainingDelayMs = Math.max(0, intervalMs - elapsedMs)
    await waitForNextFrame(remainingDelayMs, signal)
  }
}
