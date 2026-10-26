export type DetectionResult = {
  captured_at_ms: number
  ear: number | null
  fatigue_probability: number | null
  fsr_raw: number | null
  tof_distance_mm: number | null
  present: boolean | null
  minute: {
    valid_samples: number
    drowsy_samples: number
    unavailable_samples: number
    window_seconds: 60
  }
  alert: boolean
  face_detected: boolean
}

export type StreamDiagnostics = {
  received_frames: number
  processed_frames: number
  replaced_frames: number
  stale_frames: number
  received_fps: number
  processed_fps: number
  upload_kbps: number
  last_received_frame_id: number
  pending_frames: number
  in_flight: boolean
}

export type StreamStatus = {
  type: 'status'
  detection: DetectionResult | null
  diagnostics: StreamDiagnostics | null
  mqtt_alert_sent_recently?: boolean
}

export type StreamError = {
  type: 'error'
  code: string
}

export type StreamStatusSnapshot = StreamStatus & { resultAgeMs: number | null }

export type StreamDiagnosticsSnapshot = StreamDiagnostics & {
  resultAgeMs: number | null
}

export type ServerToClientEvents = {
  status: (data: StreamStatus) => void
  stream_error: (data: StreamError) => void
}

export type ClientToServerEvents = {
  frame: (payload: Blob) => void
}
