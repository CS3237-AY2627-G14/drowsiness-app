import { useCallback, useEffect, useRef } from 'react'
import { streamFrames } from '../streamFrames'
import { getStreamingErrorMessage } from '../utils/streaming'
import { getStreamingPhase } from '../streaming.logic'
import { useCamera } from './useCamera'
import { useFrameStream } from './useFrameStream'
import type { PublishTarget } from '../types/frameStream.types.ts'

export const useStreaming = () => {
  const camera = useCamera()
  const stream = useFrameStream()
  const samplingRef = useRef<AbortController | null>(null)
  const { open: openCamera, close: closeCamera, captureFrame } = camera
  const {
    connect,
    close: closeStream,
    stopWithError,
    canSendFrame,
    sendFrame,
  } = stream

  const stopSampling = useCallback(() => {
    samplingRef.current?.abort()
    samplingRef.current = null
  }, [])

  const stop = useCallback(() => {
    stopSampling()
    closeStream()
    closeCamera()
  }, [stopSampling, closeStream, closeCamera])

  const startCamera = async (deviceId?: string) => {
    stop()
    await openCamera(deviceId)
  }

  const publish = async (target: PublishTarget) => {
    if (!camera.isOpen || samplingRef.current !== null) return
    const controller = new AbortController()
    samplingRef.current = controller
    const releaseSamplingOperation = () => {
      if (samplingRef.current === controller) samplingRef.current = null
    }
    const connected = await connect(target)
    if (!connected || controller.signal.aborted) {
      releaseSamplingOperation()
      return
    }
    const handleSamplingError = (cause: unknown) => {
      if (samplingRef.current === controller) stopWithError(cause)
    }
    const sampling = streamFrames({
      captureFrame,
      connection: { canSendFrame, sendFrame },
      signal: controller.signal,
    })
    const handledSampling = sampling.catch(handleSamplingError)
    await handledSampling.finally(releaseSamplingOperation)
  }

  useEffect(() => {
    if (camera.error !== null) {
      stopSampling()
      closeStream()
    } else if (stream.error !== null) {
      stopSampling()
    }
  }, [camera.error, stream.error, stopSampling, closeStream])

  useEffect(() => {
    window.addEventListener('pagehide', stop)
    return () => {
      window.removeEventListener('pagehide', stop)
      stopSampling()
    }
  }, [stop, stopSampling])

  const cause = camera.error ?? stream.error
  const error = cause === null ? null : getStreamingErrorMessage(cause)
  const phase = getStreamingPhase({
    cameraLoading: camera.isLoading,
    cameraOpen: camera.isOpen,
    streamLoading: stream.isLoading,
    streamConnected: stream.isConnected,
    error,
  })
  const canStartCamera =
    phase === 'idle' || (phase === 'error' && !camera.isOpen)
  const canPublish =
    camera.isOpen && (phase === 'preview' || phase === 'streamError')
  return {
    videoRef: camera.videoRef,
    canvasRef: camera.canvasRef,
    phase,
    error,
    metrics: stream.status?.diagnostics
      ? { ...stream.status.diagnostics, resultAgeMs: stream.status.resultAgeMs }
      : null,
    detection: stream.status?.detection ?? null,
    mqttAlertSentRecently: stream.status?.mqtt_alert_sent_recently ?? false,
    hasPreview: camera.isOpen,
    canStartCamera,
    canPublish,
    canStop: !canStartCamera,
    canChangeTarget: canStartCamera || canPublish,
    startCamera,
    publish,
    stop,
  }
}
