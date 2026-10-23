import type { DetectionStatusProps } from '../PublishPage.types'

const getDetectionLabel = (
  detection: DetectionStatusProps['detection'],
): string => {
  if (!detection) return 'Waiting for detection'
  if (detection.minute.valid_samples < 30) return 'Gathering observations'
  return detection.alert ? 'Drowsiness detected' : 'Monitoring'
}

const formatFatigueProbability = (
  probability: number | null | undefined,
): string => {
  if (probability == null) return '—'
  const percentage = probability * 100
  return `${percentage.toFixed(0)}%`
}

export const DetectionStatus = ({ detection }: DetectionStatusProps) => {
  const minute = detection?.minute
  const label = getDetectionLabel(detection)
  const observations = minute
    ? `${minute.drowsy_samples} of ${minute.valid_samples} valid pictures`
    : '—'
  const eyeOpenness = detection?.ear?.toFixed(3) ?? '—'
  const fatigueProbability = formatFatigueProbability(
    detection?.fatigue_probability,
  )

  return (
    <section
      className="island-shell rounded-2xl p-4 sm:p-6"
      aria-label="Detection results"
    >
      <h2 className="text-lg font-semibold">{label}</h2>
      <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
        <div>
          <dt>Drowsy pictures in the last minute</dt>
          <dd>{observations}</dd>
        </div>
        <div>
          <dt>Seconds without a valid picture</dt>
          <dd>{minute?.unavailable_samples ?? '—'}</dd>
        </div>
        <div>
          <dt>Eye openness (EAR)</dt>
          <dd>{eyeOpenness}</dd>
        </div>
        <div>
          <dt>CNN fatigue probability</dt>
          <dd>{fatigueProbability}</dd>
        </div>
        <div>
          <dt>FSR reading (raw)</dt>
          <dd>{detection?.fsr_raw ?? '—'}</dd>
        </div>
        <div>
          <dt>ToF distance</dt>
          <dd>
            {detection?.tof_distance_mm == null
              ? '—'
              : `${detection.tof_distance_mm} mm`}
          </dd>
        </div>
        <div>
          <dt>Present</dt>
          <dd>
            {detection?.present == null
              ? '—'
              : detection.present
                ? 'Yes'
                : 'No'}
          </dd>
        </div>
      </dl>
      <p className="mt-4 text-xs text-[var(--sea-ink-soft)]">
        One picture per second counts toward the minute. An alert needs at least
        30 valid pictures, with half or more showing signs of drowsiness.
        Missing pictures do not count as awake. A fresh FSR reading of zero
        marks the seat unoccupied; ToF is shown for monitoring and does not yet
        affect the drowsiness classification.
      </p>
      {detection?.fsr_raw === 0 ? (
        <p className="mt-2 text-sm">Seat unoccupied.</p>
      ) : detection && !detection.face_detected ? (
        <p className="mt-2 text-sm">No face detected in the latest picture.</p>
      ) : null}
    </section>
  )
}
