import { io } from 'socket.io-client'
import type { Socket } from 'socket.io-client'
import { encodeFrame, getStreamErrorMessage } from './utils/frameStream'
import type { CapturedFrame } from './types/camera.types'
import type {
  ConnectFrameStreamOptions,
  FrameStreamConnection,
} from './types/frameStream.types'
import type {
  StreamError,
  ServerToClientEvents,
  ClientToServerEvents,
} from './types/protocol.types'

export const connectFrameStream = async ({
  seatId,
  token,
  signal,
  onStatus,
  onError,
}: ConnectFrameStreamOptions): Promise<FrameStreamConnection> => {
  signal.throwIfAborted()
  const socket: Socket<ServerToClientEvents, ClientToServerEvents> = io(
    window.location.origin,
    {
      path: '/api/socket.io',
      transports: ['websocket'],
      auth: { seat_id: seatId, token, diagnostics: import.meta.env.DEV },
      autoConnect: false,
      reconnection: false,
      forceNew: true,
      timeout: 5000,
    },
  )
  let connected = false
  let closed = false
  let nextFrameId = 1
  let resolveConnection: () => void
  let rejectConnection: (error: Error) => void
  const connection = new Promise<void>((resolve, reject) => {
    resolveConnection = resolve
    rejectConnection = reject
  })

  const close = () => {
    if (closed) return
    closed = true
    signal.removeEventListener('abort', close)
    socket.removeAllListeners()
    socket.auth = {}
    if (!connected) {
      const cancellation = new DOMException('Cancelled', 'AbortError')
      rejectConnection(cancellation)
    }
    socket.disconnect()
  }
  const disconnectWithError = (error: Error) => {
    if (closed) return
    if (!connected) rejectConnection(error)
    close()
    if (connected) onError(error)
  }
  const handleStreamError = (message: StreamError) => {
    const errorMessage = getStreamErrorMessage(message.code)
    const error = new Error(errorMessage)
    disconnectWithError(error)
  }
  const handleConnectionError = (
    error: Error & { data?: { code: string } },
  ) => {
    if (error.data) handleStreamError({ type: 'error', code: error.data.code })
    else handleDisconnect()
  }

  const handleConnect = () => {
    connected = true
    socket.auth = {}
    resolveConnection()
  }
  const handleDisconnect = () => {
    const error = new Error(
      'Cannot reach the streaming service. Check the API server.',
    )
    disconnectWithError(error)
  }

  socket.on('connect', handleConnect)
  socket.on('status', onStatus)
  socket.on('stream_error', handleStreamError)
  socket.on('connect_error', handleConnectionError)
  socket.on('disconnect', handleDisconnect)
  signal.addEventListener('abort', close, { once: true })
  socket.connect()
  await connection

  const canSendFrame = () =>
    !signal.aborted && socket.connected && socket.io.engine.transport.writable
  const sendFrame = (frame: CapturedFrame) => {
    if (!canSendFrame()) return false
    const frameId = nextFrameId++
    const payload = encodeFrame(frameId, frame)
    socket.volatile.emit('frame', payload)
    return true
  }
  return { canSendFrame, sendFrame }
}
