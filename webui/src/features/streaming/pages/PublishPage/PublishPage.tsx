import { useEffect } from 'react'
import type { ChangeEvent } from 'react'
import { Button } from '#/components/ui/Button'
import { useStreaming } from '../../hooks/useStreaming'
import { useClassrooms } from '../../hooks/useClassrooms'
import { usePublishTarget } from './hooks/usePublishTarget'
import { CameraPreview } from './components/CameraPreview'
import { ConnectionStatus } from './components/ConnectionStatus'
import { PublishControls } from './components/PublishControls'
import { SeatSelector } from './components/SeatSelector'
import { StreamMetrics } from './components/StreamMetrics'
import { DetectionStatus } from './components/DetectionStatus'

export const PublishPage = () => {
  const {
    data: classrooms = [],
    isError: hasClassroomsError,
    isPending: isLoadingClassrooms,
    refetch: refetchClassrooms,
  } = useClassrooms()
  const streaming = useStreaming()
  const { room, seat, token, selectRoom, selectSeat, setToken } =
    usePublishTarget(classrooms)
  const showDiagnostics = import.meta.env.DEV
  const isTargetSelectionLocked = !streaming.canChangeTarget
  const { stop } = streaming

  useEffect(() => stop, [room?.id, seat?.id, stop])

  const canStartCamera = streaming.canStartCamera && Boolean(seat)
  const canPublish =
    streaming.canPublish && Boolean(seat) && Boolean(token.trim())
  const showClassroomsMessage = !room && !hasClassroomsError
  const classroomsMessage = isLoadingClassrooms
    ? 'Loading classrooms…'
    : 'No classrooms are available.'

  const handleRetryClassrooms = () => {
    void refetchClassrooms()
  }
  const handleStartCamera = () => {
    void streaming.startCamera()
  }
  const handlePublish = () => {
    if (seat) void streaming.publish({ seatId: seat.id, token })
  }
  const handleTokenChange = (event: ChangeEvent<HTMLInputElement>) => {
    setToken(event.currentTarget.value)
  }

  return (
    <main className="page-wrap py-6 text-[var(--sea-ink)] sm:py-10">
      <header className="mb-7 flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="island-kicker mb-2">Classroom streaming test</p>
          <h1 className="display-title text-3xl sm:text-4xl">
            Classroom camera
          </h1>
          <p className="mt-3 max-w-xl text-sm text-[var(--sea-ink-soft)] sm:text-base">
            Choose your seat and check your video before publishing.
          </p>
        </div>
        <ConnectionStatus phase={streaming.phase} />
      </header>

      {hasClassroomsError ? (
        <div
          role="alert"
          className="mb-5 rounded-xl border border-red-200 bg-red-50 p-4 text-red-900"
        >
          <p>Could not load classrooms. Please try again.</p>
          <Button
            type="button"
            variant="outline"
            className="mt-3"
            onClick={handleRetryClassrooms}
          >
            Retry classrooms
          </Button>
        </div>
      ) : null}
      {streaming.error ? (
        <p
          role="alert"
          className="mb-5 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-900"
        >
          {streaming.error}
        </p>
      ) : null}

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="order-2 grid min-w-0 gap-5 lg:order-1">
          <CameraPreview
            videoRef={streaming.videoRef}
            canvasRef={streaming.canvasRef}
            active={streaming.hasPreview}
          />
          {showDiagnostics ? (
            <StreamMetrics metrics={streaming.metrics} />
          ) : null}
          <DetectionStatus detection={streaming.detection} />
        </div>
        <aside
          className="island-shell order-1 grid gap-6 rounded-2xl p-5 lg:order-2 sm:p-6"
          aria-label="Streaming controls"
        >
          {room ? (
            <SeatSelector
              classrooms={classrooms}
              room={room}
              seatId={seat?.id ?? null}
              disabled={isTargetSelectionLocked}
              onRoomChange={selectRoom}
              onSeatChange={selectSeat}
            />
          ) : null}
          {showClassroomsMessage ? (
            <p role="status" className="text-sm">
              {classroomsMessage}
            </p>
          ) : null}
          <PublishControls
            canStartCamera={canStartCamera}
            canPublish={canPublish}
            canStop={streaming.canStop}
            onStart={handleStartCamera}
            onPublish={handlePublish}
            onStop={stop}
          />
          <details className="border-t border-[var(--line)] pt-4">
            <summary className="cursor-pointer text-sm font-semibold">
              Demo credentials
            </summary>
            <p className="my-3 text-xs leading-5 text-[var(--sea-ink-soft)]">
              A development token is filled in for your seat. Edit it to test
              rejected access.
            </p>
            <label htmlFor="session-token" className="text-sm font-medium">
              Session token
            </label>
            <input
              id="session-token"
              type="password"
              autoComplete="off"
              spellCheck={false}
              disabled={isTargetSelectionLocked}
              value={token}
              onChange={handleTokenChange}
              className="form-control mt-1.5 w-full"
            />
          </details>
        </aside>
      </div>
      <p className="mt-6 text-xs leading-5 text-[var(--sea-ink-soft)]">
        Full camera frames are processed on the server using CNN and
        eye-openness detection.
      </p>
    </main>
  )
}
