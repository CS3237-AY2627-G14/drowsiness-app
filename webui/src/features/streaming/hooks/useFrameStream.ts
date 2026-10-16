import { useCallback, useEffect, useRef, useState } from 'react'
import { createFrameStream } from '../frameStream'
import { normalizeStreamingError } from '../utils/streaming'
import type { CapturedFrame } from '../types/camera.types'
import type {
  FrameStream,
  FrameStreamControls,
  PublishTarget,
} from '../types/frameStream.types'
import type { ResourceRequestResult } from '../types/streaming.types'
import type { StreamStatusSnapshot } from '../types/protocol.types'

export const useFrameStream = (): FrameStreamControls => {
  const streamRef = useRef<FrameStream | null>(null)
  const activeRequestRef = useRef<symbol | null>(null)
  const [request, setRequest] = useState<ResourceRequestResult | null>(null)
  const [status, setStatus] = useState<StreamStatusSnapshot | null>(null)

  const stopWithError = useCallback((cause: unknown) => {
    if (activeRequestRef.current === null) return
    activeRequestRef.current = null
    streamRef.current?.close()
    const error = normalizeStreamingError(cause)
    setRequest({ pending: false, error })
    setStatus(null)
  }, [])

  const close = useCallback(() => {
    activeRequestRef.current = null
    streamRef.current?.close()
    setRequest(null)
    setStatus(null)
  }, [])

  const connect = async (target: PublishTarget): Promise<boolean> => {
    if (activeRequestRef.current !== null) return false
    const stream = streamRef.current
    if (!stream) return false
    const id = Symbol('connection request')
    activeRequestRef.current = id
    setRequest({ pending: true, error: null })
    setStatus(null)
    try {
      await stream.connect(target)
      if (activeRequestRef.current !== id) return false
      setRequest({ pending: false, error: null })
      return true
    } catch (cause) {
      if (activeRequestRef.current === id) stopWithError(cause)
      return false
    }
  }

  const canSendFrame = () => streamRef.current?.canSendFrame() ?? false
  const sendFrame = (frame: CapturedFrame): boolean => {
    const stream = streamRef.current
    if (stream === null) return false
    try {
      return stream.sendFrame(frame)
    } catch (cause) {
      stopWithError(cause)
      return false
    }
  }

  useEffect(() => {
    const stream = createFrameStream({
      onStatus: (message) => {
        if (activeRequestRef.current === null) return
        setStatus({
          ...message,
          resultAgeMs: message.detection
            ? performance.now() - message.detection.captured_at_ms
            : null,
        })
      },
      onInterrupted: stopWithError,
    })

    streamRef.current = stream
    return () => {
      activeRequestRef.current = null
      stream.close()
      streamRef.current = null
    }
  }, [stopWithError])

  const error = request?.error ?? null
  return {
    stopWithError,
    connect,
    close,
    canSendFrame,
    sendFrame,
    isLoading: request?.pending ?? false,
    isConnected: request !== null && !request.pending && error === null,
    error,
    isError: error !== null,
    status,
  }
}
