export type DetectionResult = {
  captured_at_ms: number
  ear: number | null
  fatigue_probability: number | null
  sensor_drowsy: boolean | null
  present: boolean | null
  minute: {
    valid_samples: number
    drowsy_samples: number
    unavailable_samples: number
    window_seconds: 60
  }
  alert: boolean
  face_detected: boolean
  sensor_score?: number | null
  sensor_model_version?: string | null
  sensor_unavailable_reason?: string | null
}

export type DetectionDebug = {
  confirmed_state: 'monitoring' | 'drowsy' | 'unavailable'
  phase:
    | 'stable'
    | 'entering_drowsy'
    | 'recovering'
    | 'unknown_grace'
    | 'unavailable'
  current_drowsy: boolean | null
  drowsy_seconds: number
  awake_seconds: number
  unknown_seconds: number
  entry_required_seconds: number
  recovery_required_seconds: number
  unknown_timeout_seconds: number
  camera_age_seconds: number | null
  sensor_age_seconds: number | null
  reason: string | null
}

export type StreamDiagnostics = {
  detection_state?: DetectionDebug | null
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
