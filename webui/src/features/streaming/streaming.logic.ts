import type {
  StreamingPhase,
  StreamingPhaseInput,
} from './types/streaming.types'

export const getStreamingPhase = ({
  cameraLoading,
  cameraOpen,
  streamLoading,
  streamConnected,
  error,
}: StreamingPhaseInput): StreamingPhase => {
  if (error !== null) return cameraOpen ? 'streamError' : 'error'
  if (cameraLoading) return 'requestingCamera'
  if (!cameraOpen) return 'idle'
  if (streamLoading) return 'connecting'
  if (streamConnected) return 'live'
  return 'preview'
}
