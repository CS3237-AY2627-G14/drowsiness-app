import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { createCamera } from './camera'
import type { CameraPreviewElements } from './types/camera.types'

const createMedia = () => {
  const trackEvents = new EventTarget()
  const stop = vi.fn()
  const track = Object.assign(trackEvents, { stop })
  const stream = {
    getTracks: () => [track],
    getVideoTracks: () => [track],
  } as unknown as MediaStream
  return { stream, track }
}

const createPreview = () => {
  const context = { fillStyle: '', fillRect: vi.fn(), drawImage: vi.fn() }
  const video = {
    srcObject: null as MediaStream | null,
    muted: false,
    playsInline: false,
    videoWidth: 1280,
    videoHeight: 720,
    readyState: 2,
    paused: false,
    play: vi.fn(async () => {}),
    pause: vi.fn(),
  }
  const canvas = {
    width: 1280,
    height: 720,
    getContext: vi.fn(() => context),
    toBlob: vi.fn((callback: BlobCallback) => {
      const jpeg = new Blob(['jpeg'], { type: 'image/jpeg' })
      callback(jpeg)
    }),
  }
  const elements = { video, canvas } as unknown as CameraPreviewElements
  return { video, canvas, context, elements }
}

const getUserMedia = vi.fn<() => Promise<MediaStream>>()

beforeEach(() => {
  vi.clearAllMocks()
  vi.stubGlobal('window', { isSecureContext: true })
  vi.stubGlobal('navigator', { mediaDevices: { getUserMedia } })
})

afterEach(() => vi.unstubAllGlobals())

it('shares acquisition, captures full frames, and releases the camera once', async () => {
  const media = createMedia()
  getUserMedia.mockResolvedValue(media.stream)
  const preview = createPreview()
  const onCameraEnded = vi.fn()
  const camera = createCamera(onCameraEnded)
  const opening = camera.open(preview.elements)
  expect(camera.open(preview.elements)).toBe(opening)
  await opening
  expect(getUserMedia).toHaveBeenCalledTimes(1)
  expect(preview.video.srcObject).toBe(media.stream)
  const frame = await camera.captureFrame()
  expect(frame?.jpeg.type).toBe('image/jpeg')
  expect(preview.context.drawImage).toHaveBeenCalledWith(
    preview.video,
    0,
    0,
    1280,
    720,
  )
  camera.close()
  camera.close()
  expect(media.track.stop).toHaveBeenCalledTimes(1)
  expect(preview.video.srcObject).toBeNull()
  expect(await camera.captureFrame()).toBeNull()
})

it('preserves permission errors and permits another acquisition', async () => {
  const denied = new DOMException('Denied', 'NotAllowedError')
  getUserMedia.mockRejectedValueOnce(denied)
  const onCameraEnded = vi.fn()
  const camera = createCamera(onCameraEnded)
  const preview = createPreview()
  await expect(camera.open(preview.elements)).rejects.toBe(denied)
  const media = createMedia()
  getUserMedia.mockResolvedValueOnce(media.stream)
  await camera.open(preview.elements)
  expect(preview.video.srcObject).toBe(media.stream)
  camera.close()
})

it('cancels immediately and releases a camera granted after close without replacing a restart', async () => {
  let grantPermission: (stream: MediaStream) => void = () => {}
  getUserMedia.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        grantPermission = resolve
      }),
  )
  const onCameraEnded = vi.fn()
  const camera = createCamera(onCameraEnded)
  const preview = createPreview()
  const opening = camera.open(preview.elements)
  const cancellation = expect(opening).rejects.toMatchObject({
    name: 'AbortError',
  })
  camera.close()
  await cancellation
  const restarted = createMedia()
  getUserMedia.mockResolvedValueOnce(restarted.stream)
  await camera.open(preview.elements)
  const late = createMedia()
  grantPermission(late.stream)
  await vi.waitFor(() => expect(late.track.stop).toHaveBeenCalledOnce())
  expect(preview.video.srcObject).toBe(restarted.stream)
  expect(restarted.track.stop).not.toHaveBeenCalled()
  camera.close()
})

it('releases tracks when closed during video playback setup', async () => {
  const media = createMedia()
  getUserMedia.mockResolvedValue(media.stream)
  const preview = createPreview()
  let finishPlayback: () => void = () => {}
  preview.video.play.mockImplementation(
    () =>
      new Promise<void>((resolve) => {
        finishPlayback = resolve
      }),
  )
  const onCameraEnded = vi.fn()
  const camera = createCamera(onCameraEnded)
  const opening = camera.open(preview.elements)
  const cancellation = expect(opening).rejects.toMatchObject({
    name: 'AbortError',
  })
  await vi.waitFor(() => expect(preview.video.play).toHaveBeenCalledOnce())
  camera.close()
  await cancellation
  finishPlayback()
  await Promise.resolve()
  expect(media.track.stop).toHaveBeenCalledTimes(1)
  expect(preview.video.srcObject).toBeNull()
})

it('discards an encoded frame completed after closing the camera', async () => {
  const media = createMedia()
  getUserMedia.mockResolvedValue(media.stream)
  const preview = createPreview()
  const onCameraEnded = vi.fn()
  const camera = createCamera(onCameraEnded)
  await camera.open(preview.elements)
  let finishEncoding: BlobCallback = () => {}
  preview.canvas.toBlob.mockImplementation((callback) => {
    finishEncoding = callback
  })
  const frame = camera.captureFrame()
  camera.close()
  const jpeg = new Blob(['jpeg'], { type: 'image/jpeg' })
  finishEncoding(jpeg)
  expect(await frame).toBeNull()
})

it('reports a camera interruption once and closes its resources', async () => {
  const media = createMedia()
  getUserMedia.mockResolvedValue(media.stream)
  const onEnded = vi.fn()
  const camera = createCamera(onEnded)
  const preview = createPreview()
  await camera.open(preview.elements)
  const cameraEnded = new Event('ended')
  media.track.dispatchEvent(cameraEnded)
  const repeatedCameraEnded = new Event('ended')
  media.track.dispatchEvent(repeatedCameraEnded)
  expect(onEnded).toHaveBeenCalledOnce()
  expect(media.track.stop).toHaveBeenCalledOnce()
  expect(await camera.captureFrame()).toBeNull()
})

it('requests the selected camera exactly without imposing the upload frame rate', async () => {
  const media = createMedia()
  getUserMedia.mockResolvedValueOnce(media.stream)
  const preview = createPreview()
  const camera = createCamera(vi.fn())
  await camera.open({ ...preview.elements, deviceId: 'remote-camera' })
  expect(getUserMedia).toHaveBeenCalledWith({
    audio: false,
    video: {
      width: { ideal: 1280 },
      height: { ideal: 720 },
      deviceId: { exact: 'remote-camera' },
      resizeMode: { ideal: 'none' },
    },
  })
  camera.close()
})

it('reports a missing selected camera without opening a different camera', async () => {
  const missing = new DOMException(
    'Selected camera disconnected',
    'NotFoundError',
  )
  getUserMedia.mockRejectedValueOnce(missing)
  const preview = createPreview()
  const camera = createCamera(vi.fn())
  await expect(
    camera.open({ ...preview.elements, deviceId: 'disconnected-camera' }),
  ).rejects.toBe(missing)
  expect(getUserMedia).toHaveBeenCalledOnce()
  expect(preview.video.srcObject).toBeNull()
})
