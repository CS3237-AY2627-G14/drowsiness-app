import type { PublishControlsProps } from '../PublishPage.types'
import { Button } from '#/components/ui/Button'

export const PublishControls = ({
  canStartCamera,
  canPublish,
  canStop,
  onStart,
  onPublish,
  onStop,
}: PublishControlsProps) => {
  return (
    <div className="grid gap-2.5">
      <Button
        type="button"
        disabled={!canStartCamera}
        onClick={onStart}
        className="min-h-11 w-full"
      >
        Start camera
      </Button>
      <Button
        type="button"
        disabled={!canPublish}
        onClick={onPublish}
        className="min-h-11 w-full bg-[var(--palm)] text-white hover:bg-[var(--sea-ink)]"
      >
        Publish
      </Button>
      <Button
        type="button"
        variant="outline"
        disabled={!canStop}
        onClick={onStop}
        className="min-h-11 w-full"
      >
        Stop
      </Button>
    </div>
  )
}
