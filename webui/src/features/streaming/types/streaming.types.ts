export type StreamingPhase =
  | 'idle'
  | 'requestingCamera'
  | 'preview'
  | 'connecting'
  | 'live'
  | 'streamError'
  | 'error'

export type ResourceRequestResult = {
  pending: boolean
  error: Error | null
}

export type StreamingPhaseInput = {
  cameraLoading: boolean
  cameraOpen: boolean
  streamLoading: boolean
  streamConnected: boolean
  error: string | null
}
