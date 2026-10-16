import type { CapturedFrame } from '../types/camera.types'

const errorMessages: Record<string, string> = {
  unauthorized:
    'Publishing was not authorized. Check the token and selected seat.',
  seat_busy: 'This seat already has an active publisher.',
  capacity_reached: 'The server has reached its camera limit.',
  session_expired: 'The publishing session expired. Start a new session.',
  invalid_frame: 'The server rejected a camera frame.',
  stream_idle: 'The camera stopped sending frames. Please retry.',
  server_unavailable: 'Detection is unavailable. Please retry.',
}

export const getStreamErrorMessage = (code: string): string =>
  errorMessages[code] ?? 'Streaming was interrupted. Please retry.'

export const encodeFrame = (frameId: number, frame: CapturedFrame): Blob => {
  const header = new ArrayBuffer(12)
  const view = new DataView(header)
  view.setUint32(0, frameId, false)
  view.setFloat64(4, frame.capturedAtMs, false)
  return new Blob([header, frame.jpeg])
}
