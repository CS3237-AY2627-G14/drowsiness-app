import type { DetectionStatusProps } from '../PublishPage.types'

const getDetectionLabel = (
  detection: DetectionStatusProps['detection'],
): string => {
  if (!detection) return 'Waiting for detection'
  if (detection.minute.valid_samples < 10) return 'Gathering observations'
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
  const validSampleProgress = minute ? `${minute.valid_samples} / 10` : '—'
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
          <dt>Valid samples (10 minimum)</dt>
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
          <dt>ESP32 drowsy result</dt>
          <dd>
            {detection?.sensor_drowsy == null
              ? '—'
              : detection.sensor_drowsy
                ? 'Drowsy'
                : 'Not drowsy'}
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
        10 valid pictures, with half or more showing signs of drowsiness.
        Missing sensor readings and unoccupied seats do not count. An ESP32
        drowsy result is counted as drowsy when the camera also detects
        drowsiness or no face is detected; a detected awake face overrides the
        ESP32 result. The MQTT indicator reflects a successful publish in the
        last 10 seconds.
      </p>
      {detection?.present === false ? (
        <p className="mt-2 text-sm">Seat unoccupied.</p>
      ) : detection && !detection.face_detected ? (
        <p className="mt-2 text-sm">No face detected in the latest picture.</p>
      ) : null}
    </section>
  )
}
