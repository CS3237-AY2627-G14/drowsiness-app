import { videoConfig } from '#/lib/config'
import { calculatePaddedFrameLayout } from './utils/camera'
import type { CameraCapture, CapturedFrame } from './types/camera.types'

const encodeCanvasJpeg = (canvas: HTMLCanvasElement): Promise<Blob> =>
  new Promise<Blob>((resolve, reject) => {
    const handleEncodedFrame = (blob: Blob | null) => {
      if (blob && blob.type === 'image/jpeg') {
        resolve(blob)
        return
      }
      const error = new Error('The browser could not encode a JPEG frame.')
      reject(error)
    }
    canvas.toBlob(handleEncodedFrame, 'image/jpeg', videoConfig.jpegQuality)
  })

export const openCameraCapture = async (
  video: HTMLVideoElement,
  canvas: HTMLCanvasElement,
  signal: AbortSignal,
  onCameraEnded: () => void,
): Promise<CameraCapture> => {
  if (
    !window.isSecureContext ||
    typeof navigator.mediaDevices === 'undefined' ||
    typeof navigator.mediaDevices.getUserMedia !== 'function'
  )
    throw new Error('Camera access requires trusted HTTPS or localhost.')
  const context = canvas.getContext('2d', { alpha: false })
  if (!context)
    throw new Error('Video processing is unavailable in this browser.')

  const constraints = {
    width: { ideal: videoConfig.width },
    height: { ideal: videoConfig.height },
    frameRate: { ideal: videoConfig.frameRate, max: videoConfig.frameRate },
    facingMode: { ideal: 'user' },
    resizeMode: { ideal: 'none' },
  }
  const camera = await navigator.mediaDevices.getUserMedia({
    audio: false,
    video: constraints,
  })
  let released = false
  const releaseCamera = () => {
    if (released) return
    released = true
    signal.removeEventListener('abort', releaseCamera)
    for (const track of camera.getTracks()) {
      track.removeEventListener('ended', onCameraEnded)
      track.stop()
    }
    if (video.srcObject === camera) {
      video.pause()
      video.srcObject = null
      context.fillStyle = '#101d22'
      context.fillRect(0, 0, canvas.width, canvas.height)
    }
  }
  signal.addEventListener('abort', releaseCamera, { once: true })
  try {
    signal.throwIfAborted()
    video.muted = true
    video.playsInline = true
    video.srcObject = camera
    await video.play()
    signal.throwIfAborted()
    canvas.width = videoConfig.width
    canvas.height = videoConfig.height
    const drawPaddedFrame = () => {
      const layout = calculatePaddedFrameLayout(
        video.videoWidth,
        video.videoHeight,
        canvas.width,
        canvas.height,
      )
      context.fillStyle = '#101d22'
      context.fillRect(0, 0, canvas.width, canvas.height)
      context.drawImage(video, layout.x, layout.y, layout.width, layout.height)
    }
    drawPaddedFrame()
    for (const track of camera.getVideoTracks())
      track.addEventListener('ended', onCameraEnded)
    const captureFrame = async (): Promise<CapturedFrame | null> => {
      if (video.readyState < 2 || video.paused) return null
      const capturedAtMs = performance.now()
      drawPaddedFrame()
      const jpeg = await encodeCanvasJpeg(canvas)
      if (signal.aborted) return null
      return { capturedAtMs, jpeg }
    }
    return { captureFrame }
  } catch (error) {
    releaseCamera()
    throw error
  }
}
