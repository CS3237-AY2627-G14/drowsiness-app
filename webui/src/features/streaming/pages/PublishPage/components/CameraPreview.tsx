import type { CameraPreviewProps } from '../PublishPage.types'
import { videoConfig } from '#/lib/config'

export const CameraPreview = ({
  videoRef,
  canvasRef,
  active,
}: CameraPreviewProps) => {
  const canvasStyle = {
    aspectRatio: `${videoConfig.width} / ${videoConfig.height}`,
  }
  return (
    <section
      aria-label="Video previews"
      className="island-shell rounded-2xl p-4 sm:p-6"
    >
      <div className="mb-5 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold">Check your framing</h2>
        <span className="text-sm text-[var(--sea-ink-soft)]">
          Full frame · no crop
        </span>
      </div>
      <div className="grid gap-5 sm:grid-cols-2">
        <figure>
          <div className="video-surface">
            <video
              ref={videoRef}
              muted
              playsInline
              aria-label="Camera preview"
              className="h-full w-full object-contain"
            />
            {!active ? (
              <div className="video-placeholder">
                Start your camera to preview.
              </div>
            ) : null}
          </div>
          <figcaption className="mt-3 text-sm font-semibold">
            Camera feed
          </figcaption>
          <p className="mt-1 text-xs text-[var(--sea-ink-soft)]">
            Visible only on this device until you publish.
          </p>
        </figure>
        <figure>
          <div className="video-surface" style={canvasStyle}>
            <canvas
              ref={canvasRef}
              width={videoConfig.width}
              height={videoConfig.height}
              role="img"
              aria-label="Full-frame outgoing video preview"
              className="h-full w-full object-contain"
            >
              Your browser needs canvas support.
            </canvas>
            {!active ? (
              <div className="video-placeholder">
                Your outgoing video appears here.
              </div>
            ) : null}
          </div>
          <figcaption className="mt-3 text-sm font-semibold">
            Latest captured frame
          </figcaption>
          <p className="mt-1 text-xs text-[var(--sea-ink-soft)]">
            Captured with padding to preserve the complete frame.
          </p>
        </figure>
      </div>
    </section>
  )
}
