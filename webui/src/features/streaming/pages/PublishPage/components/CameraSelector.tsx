import type { ChangeEvent } from 'react'
import { Button } from '#/components/ui/Button'

type CameraSelectorProps = {
  cameras: MediaDeviceInfo[]
  deviceId: string
  disabled: boolean
  isRefreshing: boolean
  canEnumerate: boolean
  hasError: boolean
  onChange: (deviceId: string) => void
  onRefresh: () => void
}

export const CameraSelector = ({
  cameras,
  deviceId,
  disabled,
  isRefreshing,
  canEnumerate,
  hasError,
  onChange,
  onRefresh,
}: CameraSelectorProps) => {
  const isSelectedCameraMissing =
    deviceId !== '' && !cameras.some((camera) => camera.deviceId === deviceId)
  const handleChange = (event: ChangeEvent<HTMLSelectElement>) => {
    onChange(event.currentTarget.value)
  }

  return (
    <div className="grid min-w-0 gap-2">
      <label htmlFor="camera-device" className="text-sm font-medium">
        Camera
      </label>
      <select
        id="camera-device"
        className="form-control w-full min-w-0 max-w-full"
        value={deviceId}
        disabled={disabled || !canEnumerate}
        onChange={handleChange}
        aria-describedby="camera-help"
      >
        <option value="">Browser default camera</option>
        {isSelectedCameraMissing ? (
          <option value={deviceId}>Selected camera unavailable</option>
        ) : null}
        {cameras.map((camera, index) => (
          <option key={camera.deviceId} value={camera.deviceId}>
            {camera.label || `Camera ${index + 1}`}
          </option>
        ))}
      </select>
      <Button
        type="button"
        variant="outline"
        disabled={!canEnumerate || isRefreshing}
        onClick={onRefresh}
      >
        {isRefreshing ? 'Refreshing cameras…' : 'Refresh cameras'}
      </Button>
      <p
        id="camera-help"
        className="text-xs leading-5 text-[var(--sea-ink-soft)]"
      >
        {disabled
          ? 'Stop the camera before choosing another.'
          : 'Allow camera access to see all cameras, then stop to choose one.'}{' '}
      </p>
      {hasError ? (
        <p role="alert" className="text-xs text-red-900">
          Could not list cameras. Check browser permissions and refresh.
        </p>
      ) : null}
      {!isRefreshing && cameras.length === 0 && canEnumerate && !hasError ? (
        <p className="text-xs text-[var(--sea-ink-soft)]">
          No cameras listed yet. Connect your camera and refresh, or start the
          default camera to grant access.
        </p>
      ) : null}
    </div>
  )
}
