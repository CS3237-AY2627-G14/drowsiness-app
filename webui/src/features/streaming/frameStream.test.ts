import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { createFrameStream } from './frameStream'

const transport = vi.hoisted(() => {
  const handlers = new Map<string, (...args: Array<unknown>) => void>()
  const socket = {
    connected: true,
    auth: {} as object,
    io: { engine: { transport: { writable: true } } },
    volatile: { emit: vi.fn() },
    connect: vi.fn(),
    disconnect: vi.fn(),
    on: vi.fn((event: string, handler: (...args: Array<unknown>) => void) => {
      handlers.set(event, handler)
    }),
    removeAllListeners: vi.fn(() => handlers.clear()),
  }
  return { socket, handlers }
})

vi.mock('socket.io-client', () => ({ io: vi.fn(() => transport.socket) }))

const createTestStream = () => {
  const callbacks = { onStatus: vi.fn(), onInterrupted: vi.fn() }
  const stream = createFrameStream(callbacks)
  return { stream, callbacks }
}
const target = { seatId: 1, token: 'test-token' }

beforeEach(() => {
  vi.useFakeTimers()
  vi.clearAllMocks()
  transport.handlers.clear()
  transport.socket.connected = true
  transport.socket.disconnect.mockImplementation(() => {
    transport.socket.connected = false
  })
  transport.socket.io.engine.transport.writable = true
  const windowEvents = new EventTarget()
  const testWindow = Object.assign(windowEvents, {
    location: { origin: 'http://localhost:3000' },
  })
  vi.stubGlobal('window', testWindow)
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

it('drops frames while the transport is busy and clears resources on cancellation', async () => {
  const { stream } = createTestStream()
  const pending = stream.connect(target)
  transport.handlers.get('connect')?.()
  await pending
  expect(transport.handlers.has('ready')).toBe(false)
  const connection = stream
  const frame = { capturedAtMs: 100, jpeg: new Blob(['jpeg']) }
  transport.socket.io.engine.transport.writable = false
  expect(connection.sendFrame(frame)).toBe(false)
  expect(transport.socket.volatile.emit).not.toHaveBeenCalled()
  transport.socket.io.engine.transport.writable = true
  expect(connection.sendFrame(frame)).toBe(true)
  expect(transport.socket.volatile.emit).toHaveBeenCalledWith(
    'frame',
    expect.any(Blob),
  )
  stream.close()
  connection.close()
  expect(connection.canSendFrame()).toBe(false)
  expect(transport.socket.disconnect).toHaveBeenCalledTimes(1)
  expect(transport.handlers.size).toBe(0)
  expect(transport.socket.auth).toEqual({})
  expect(vi.getTimerCount()).toBe(0)
})

it('maps rejected authentication and cleans up the failed setup', async () => {
  const { stream } = createTestStream()
  const pending = stream.connect(target)
  const rejection = expect(pending).rejects.toThrow(
    'Publishing was not authorized',
  )
  const rejectionError = new Error('denied')
  const connectionError = Object.assign(rejectionError, {
    data: { code: 'unauthorized' },
  })
  transport.handlers.get('connect_error')?.(connectionError)
  await rejection
  expect(transport.socket.disconnect).toHaveBeenCalledTimes(1)
  expect(vi.getTimerCount()).toBe(0)
})

it('reports an unexpected disconnect once and closes the session', async () => {
  const { stream, callbacks } = createTestStream()
  const pending = stream.connect(target)
  transport.handlers.get('connect')?.()
  await pending
  const connection = stream
  transport.handlers.get('disconnect')?.('transport close')
  connection.close()
  expect(callbacks.onInterrupted).toHaveBeenCalledTimes(1)
  expect(vi.getTimerCount()).toBe(0)
})

it('cancels a pending connection and rejects without leaving timers', async () => {
  const { stream } = createTestStream()
  const pending = stream.connect(target)
  const rejection = expect(pending).rejects.toMatchObject({
    name: 'AbortError',
  })
  stream.close()
  await rejection
  expect(transport.socket.disconnect).toHaveBeenCalledTimes(1)
  expect(vi.getTimerCount()).toBe(0)
})

it('shares a pending connection and starts sending after authenticated connect without a status response', async () => {
  const { stream } = createTestStream()
  transport.socket.connected = false
  const pending = stream.connect(target)
  expect(stream.connect(target)).toBe(pending)
  const resolved = vi.fn()
  void pending.then(resolved)
  await Promise.resolve()
  expect(resolved).not.toHaveBeenCalled()
  expect(stream.canSendFrame()).toBe(false)
  transport.socket.connected = true
  transport.handlers.get('connect')?.()
  await pending
  expect(stream.canSendFrame()).toBe(true)
  stream.close()
})

it('ignores late server messages from an earlier connection', async () => {
  const { stream, callbacks } = createTestStream()
  const opening = stream.connect(target)
  transport.handlers.get('connect')?.()
  await opening
  const oldStatusHandler = transport.handlers.get('status')
  stream.close()
  transport.socket.connected = true
  const restarted = stream.connect(target)
  transport.handlers.get('connect')?.()
  await restarted
  oldStatusHandler?.({
    type: 'status',
    received_frames: 1,
    processed_frames: 1,
    replaced_frames: 0,
    stale_frames: 0,
    received_fps: 5,
    processed_fps: 5,
    upload_kbps: 100,
    last_received_frame_id: 1,
    pending_frames: 0,
    in_flight: false,
    detection: null,
  })
  expect(callbacks.onStatus).not.toHaveBeenCalled()
  stream.close()
})

it('forwards detection-only status and keeps uploading without diagnostics', async () => {
  const { stream, callbacks } = createTestStream()
  const pending = stream.connect(target)
  transport.handlers.get('connect')?.()
  await pending
  const status = { type: 'status', detection: null, diagnostics: null }
  transport.handlers.get('status')?.(status)
  expect(callbacks.onStatus).toHaveBeenCalledWith(status)
  expect(callbacks.onInterrupted).not.toHaveBeenCalled()
  const frame = { capturedAtMs: 100, jpeg: new Blob(['jpeg']) }
  expect(stream.sendFrame(frame)).toBe(true)
  stream.close()
})
