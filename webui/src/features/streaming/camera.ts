import { openCameraCapture } from './cameraCapture'
import type {
  Camera,
  CameraCapture,
  CameraOperation,
  CameraPreviewElements,
  CapturedFrame,
} from './types/camera.types'

export const createCamera = (onEnded: (error: Error) => void): Camera => {
  let operation: CameraOperation | null = null

  const close = () => {
    const previous = operation
    operation = null
    previous?.controller.abort()
  }

  const open = ({ video, canvas }: CameraPreviewElements): Promise<void> => {
    if (operation) return operation.promise
    const controller = new AbortController()
    const { signal } = controller
    const promise = new Promise<void>((resolve, reject) => {
      const handleAbort = () => {
        const cancellation = new DOMException('Cancelled', 'AbortError')
        reject(cancellation)
      }
      const handleCameraEnded = () => {
        if (signal.aborted) return
        close()
        const error = new Error('The camera was interrupted. Start it again.')
        onEnded(error)
      }
      const handleCameraOpened = (capture: CameraCapture) => {
        if (signal.aborted || operation?.controller !== controller) return
        operation.capture = capture
        resolve()
      }
      const handleCameraOpenFailed = (error: unknown) => {
        reject(error)
        if (operation?.controller === controller) close()
      }
      signal.addEventListener('abort', handleAbort, { once: true })
      const opening = openCameraCapture(
        video,
        canvas,
        signal,
        handleCameraEnded,
      )
      void opening.then(handleCameraOpened, handleCameraOpenFailed)
    })
    operation = { controller, capture: null, promise }
    return promise
  }

  const captureFrame = (): Promise<CapturedFrame | null> =>
    operation?.capture?.captureFrame() ?? Promise.resolve(null)

  return { open, captureFrame, close }
}
