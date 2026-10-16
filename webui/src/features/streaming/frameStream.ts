import { connectFrameStream } from './frameConnection'
import type { CapturedFrame } from './types/camera.types'
import type { StreamStatus } from './types/protocol.types'
import type {
  FrameStream,
  FrameStreamConnection,
  FrameStreamCallbacks,
  ConnectionOperation,
  PublishTarget,
} from './types/frameStream.types'

export const createFrameStream = ({
  onStatus,
  onInterrupted,
}: FrameStreamCallbacks): FrameStream => {
  let operation: ConnectionOperation | null = null

  const close = () => {
    const previous = operation
    operation = null
    previous?.controller.abort()
  }

  const connect = (target: PublishTarget): Promise<void> => {
    if (operation) return operation.promise
    const controller = new AbortController()
    const { signal } = controller
    const handleStatus = (status: StreamStatus) => {
      if (!signal.aborted) onStatus(status)
    }
    const handleError = (error: Error) => {
      if (signal.aborted) return
      close()
      onInterrupted(error)
    }
    const handleConnected = (connection: FrameStreamConnection) => {
      signal.throwIfAborted()
      if (operation?.controller === controller)
        operation.connection = connection
    }
    const handleConnectionFailed = (error: unknown) => {
      if (operation?.controller === controller) close()
      throw error
    }
    const connecting = connectFrameStream({
      ...target,
      signal,
      onStatus: handleStatus,
      onError: handleError,
    })
    const promise = connecting.then(handleConnected, handleConnectionFailed)
    operation = { controller, connection: null, promise }
    return promise
  }

  const canSendFrame = () => operation?.connection?.canSendFrame() ?? false
  const sendFrame = (frame: CapturedFrame) =>
    operation?.connection?.sendFrame(frame) ?? false
  return { connect, canSendFrame, sendFrame, close }
}
