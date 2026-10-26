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

export const DetectionStatus = ({
  detection,
  mqttAlertSentRecently,
}: DetectionStatusProps) => {
  const minute = detection?.minute
  const label = getDetectionLabel(detection)
  const validSampleProgress = minute ? `${minute.valid_samples} / 30` : '—'
  const drowsySampleCount = minute
    ? `${minute.drowsy_samples} of ${minute.valid_samples} valid`
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
          <dt>Valid samples (30 minimum)</dt>
          <dd>{validSampleProgress}</dd>
        </div>
        <div>
          <dt>Drowsy samples in the last minute</dt>
          <dd>{drowsySampleCount}</dd>
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
        <div>
          <dt>MQTT alert publish</dt>
          <dd aria-live="polite">
            {mqttAlertSentRecently
              ? 'Sent in the last 10 seconds'
              : 'No recent alert'}
          </dd>
        </div>
      </dl>
      <p className="mt-4 text-xs text-[var(--sea-ink-soft)]">
        One picture per second counts toward the minute. An alert needs at least
        30 valid pictures, with half or more showing signs of drowsiness.
        Missing pictures do not count as awake. A picture is classified as
        drowsy only when the camera detects drowsiness, both sensor readings are
        fresh, and FSR is above 50 or ToF distance is above 2000 mm. An FSR
        reading of zero marks the seat unoccupied. The MQTT indicator reflects
        a successful publish in the last 10 seconds.
      </p>
      {detection?.fsr_raw === 0 ? (
        <p className="mt-2 text-sm">Seat unoccupied.</p>
      ) : detection && !detection.face_detected ? (
        <p className="mt-2 text-sm">No face detected in the latest picture.</p>
      ) : null}
    </section>
  )
}
