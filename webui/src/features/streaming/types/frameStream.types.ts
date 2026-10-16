import type { CapturedFrame } from './camera.types'
import type { StreamStatus, StreamStatusSnapshot } from './protocol.types'

export type PublishTarget = { seatId: number; token: string }

export type FrameStreamConnection = {
  canSendFrame: () => boolean
  sendFrame: (frame: CapturedFrame) => boolean
}

export type ConnectFrameStreamOptions = {
  seatId: number
  token: string
  signal: AbortSignal
  onStatus: (status: StreamStatus) => void
  onError: (error: Error) => void
}

export type FrameStream = {
  connect: (target: PublishTarget) => Promise<void>
  canSendFrame: () => boolean
  sendFrame: (frame: CapturedFrame) => boolean
  close: () => void
}

export type FrameStreamCallbacks = {
  onStatus: (status: StreamStatus) => void
  onInterrupted: (error: Error) => void
}

export type ConnectionOperation = {
  controller: AbortController
  connection: FrameStreamConnection | null
  promise: Promise<void>
}

export type FrameStreamControls = {
  stopWithError: (cause: unknown) => void
  connect: (target: PublishTarget) => Promise<boolean>
  close: () => void
  canSendFrame: () => boolean
  sendFrame: (frame: CapturedFrame) => boolean
  isLoading: boolean
  isConnected: boolean
  error: Error | null
  isError: boolean
  status: StreamStatusSnapshot | null
}

export type StreamFramesOptions = {
  captureFrame: () => Promise<CapturedFrame | null>
  connection: Pick<FrameStream, 'canSendFrame' | 'sendFrame'>
  signal: AbortSignal
}
