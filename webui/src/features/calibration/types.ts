export type LabelInterval = {
  start: number
  end: number
  label: 'awake' | 'drowsy' | 'uncertain'
  posture: string
}

export type Recording = {
  id: string
  participant: string
  notes: string
  role: 'development' | 'held_out'
  started_at: number
  stopped_at: number | null
  sample_count: number
}

export type RawSample = {
  received_at: number
  telemetry: {
    upper_cm: number | null
    lower_mm: number | null
    back_adc: number
    desk_adc: number
    boot_id: string
    sequence: number
  }
}

export type RecordingDetail = {
  recording: Recording
  samples: RawSample[]
  intervals: LabelInterval[]
}

export type LiveTelemetry = {
  sample: RawSample | null
  age_seconds: number | null
  active_recording: string | null
  active_model: string | null
  candidate_model: string | null
  score: number | null
  candidate_score: number | null
  possible_drowsy: boolean | null
  present: boolean | null
  unavailable_reason: string | null
  storage_ready: boolean
}

export type Metrics = {
  recall: number | null
  awake_false_positive_rate: number | null
  true_positive: number
  false_positive: number
  true_negative: number
  false_negative: number
  unavailable: number
  samples: number
}

export type TrainingJob = {
  id: string
  status: 'running' | 'complete' | 'failed'
  error: string | null
  created_at: number
  report: {
    selected: string
    threshold: number
    coverage: number
    weak_separation: boolean
    validation: Record<string, { threshold: number; metrics: Metrics }>
    baseline: Metrics
    always_positive: Metrics
    held_out: {
      metrics: Metrics
      coverage: number
      by_posture: Record<string, Metrics>
    } | null
  } | null
}

export type Rehearsal = {
  camera_observations: number
  awake_minutes: number
  comparisons: Record<
    string,
    {
      false_alert_activations: number
      false_alerts_per_awake_minute: number | null
      alert_latency_seconds_by_drowsy_episode: (number | null)[]
      model_versions: string[]
      valid_observations: number
    }
  >
  note: string
}
