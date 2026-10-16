import { useCallback, useEffect, useRef, useState } from 'react'
import { createCamera } from '../camera'
import { normalizeStreamingError } from '../utils/streaming'
import type {
  Camera,
  CameraControls,
  CapturedFrame,
} from '../types/camera.types'
import type { ResourceRequestResult } from '../types/streaming.types'

export const useCamera = (): CameraControls => {
  const videoRef = useRef<HTMLVideoElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const cameraRef = useRef<Camera | null>(null)
  const activeRequestRef = useRef<symbol | null>(null)
  const [request, setRequest] = useState<ResourceRequestResult | null>(null)

  const recordCameraError = useCallback((cause: unknown) => {
    if (activeRequestRef.current === null) return
    activeRequestRef.current = null
    cameraRef.current?.close()
    const error = normalizeStreamingError(cause)
    setRequest({ pending: false, error })
  }, [])

  const close = useCallback(() => {
    activeRequestRef.current = null
    cameraRef.current?.close()
    setRequest(null)
  }, [])

  const open = async (): Promise<boolean> => {
    if (activeRequestRef.current !== null) return false
    const id = Symbol('camera request')
    activeRequestRef.current = id
    setRequest({ pending: true, error: null })
    const video = videoRef.current
    const canvas = canvasRef.current
    const camera = cameraRef.current
    if (!video || !canvas || !camera) {
      const error = new Error(
        'Mount the camera preview before starting the camera.',
      )
      recordCameraError(error)
      return false
    }
    try {
      await camera.open({ video, canvas })
      if (activeRequestRef.current !== id) return false
      setRequest({ pending: false, error: null })
      return true
    } catch (cause) {
      if (activeRequestRef.current === id) recordCameraError(cause)
      return false
    }
  }

  const captureFrame = async (): Promise<CapturedFrame | null> => {
    const id = activeRequestRef.current
    const camera = cameraRef.current
    if (id === null || camera === null) return null
    const frame = await camera.captureFrame()
    return activeRequestRef.current === id ? frame : null
  }

  useEffect(() => {
    const camera = createCamera(recordCameraError)
    cameraRef.current = camera
    return () => {
      activeRequestRef.current = null
      camera.close()
      cameraRef.current = null
    }
  }, [recordCameraError])

  const error = request?.error ?? null
  return {
    videoRef,
    canvasRef,
    open,
    close,
    captureFrame,
    isLoading: request?.pending ?? false,
    isOpen: request !== null && !request.pending && error === null,
    error,
    isError: error !== null,
  }
}
