import type { StreamingPhase } from '../../../types/streaming.types'

export const phaseLabels: Record<StreamingPhase, string> = {
  idle: 'Camera off',
  requestingCamera: 'Waiting for camera',
  preview: 'Preview ready',
  connecting: 'Connecting',
  live: 'Live',
  streamError: 'Publishing stopped',
  error: 'Camera unavailable',
}
