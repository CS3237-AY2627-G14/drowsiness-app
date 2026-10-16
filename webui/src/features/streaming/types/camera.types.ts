import type { RefObject } from 'react'

export type CapturedFrame = { capturedAtMs: number; jpeg: Blob }

export type CameraCapture = {
  captureFrame: () => Promise<CapturedFrame | null>
}

export type CameraPreviewElements = {
  video: HTMLVideoElement
  canvas: HTMLCanvasElement
}

export type Camera = {
  open: (preview: CameraPreviewElements) => Promise<void>
  captureFrame: () => Promise<CapturedFrame | null>
  close: () => void
}

export type CameraOperation = {
  controller: AbortController
  capture: CameraCapture | null
  promise: Promise<void>
}

export type CameraControls = {
  videoRef: RefObject<HTMLVideoElement | null>
  canvasRef: RefObject<HTMLCanvasElement | null>
  open: () => Promise<boolean>
  close: () => void
  captureFrame: () => Promise<CapturedFrame | null>
  isLoading: boolean
  isOpen: boolean
  error: Error | null
  isError: boolean
}
