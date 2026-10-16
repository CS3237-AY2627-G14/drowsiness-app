import { expect, it } from 'vitest'
import { encodeFrame } from './frameStream'

it('encodes the shared network-order frame header without base64', async () => {
  const jpegBytes = new Uint8Array([255, 216, 255])
  const jpeg = new Blob([jpegBytes])
  const frame = { capturedAtMs: 1234.5, jpeg }
  const encodedFrame = encodeFrame(42, frame)
  const payload = await encodedFrame.arrayBuffer()
  const view = new DataView(payload)
  expect(view.getUint32(0, false)).toBe(42)
  expect(view.getFloat64(4, false)).toBe(1234.5)
  const payloadBytes = new Uint8Array(payload)
  const encodedJpeg = payloadBytes.slice(12)
  expect(Array.from(encodedJpeg)).toEqual([255, 216, 255])
})
