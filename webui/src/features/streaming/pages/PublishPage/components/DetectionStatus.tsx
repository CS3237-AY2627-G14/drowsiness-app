import type { DetectionStatusProps } from '../PublishPage.types'

const getDetectionLabel = (
  detection: DetectionStatusProps['detection'],
  detectionDebug: DetectionStatusProps['detectionDebug'],
): string => {
  if (
    !detection ||
    detectionDebug?.confirmed_state === 'unavailable' ||
    detection.present === false ||
    (detection.sensor_drowsy == null && detection.minute.valid_samples === 0)
  ) {
    return 'Detection unavailable'
  }
  return detection.alert ? 'Drowsiness detected' : 'Monitoring'
}

const formatFatigueProbability = (
  probability: number | null | undefined,
): string => {
  if (probability == null) return '—'
  const percentage = probability * 100
  return `${percentage.toFixed(0)}%`
}

const formatSensorState = (value: boolean | null | undefined) => {
  if (value == null) return '—'
  return value ? 'Possible drowsy' : 'Not drowsy'
}

const formatPresence = (value: boolean | null | undefined) => {
  if (value == null) return '—'
  return value ? 'Yes' : 'No'
}

export const DetectionStatus = ({
  detection,
  detectionDebug,
  mqttAlertSentRecently,
}: DetectionStatusProps) => {
  const minute = detection?.minute
  const label = getDetectionLabel(detection, detectionDebug)
  const validSampleProgress = minute ? `${minute.valid_samples} / 60` : '—'
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
          <dt>Valid seconds in the last minute</dt>
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
          <dt>Sensor gate</dt>
          <dd>{formatSensorState(detection?.sensor_drowsy)}</dd>
        </div>
        <div>
          <dt>Sensor score / model</dt>
          <dd>
            {detection?.sensor_score?.toFixed(3) ?? '—'} /{' '}
            {detection?.sensor_model_version?.slice(0, 8) ?? 'Legacy baseline'}
          </dd>
        </div>
        {detection?.sensor_unavailable_reason && (
          <div>
            <dt>Sensor status</dt>
            <dd>{detection.sensor_unavailable_reason.replaceAll('_', ' ')}</dd>
          </div>
        )}
        <div>
          <dt>Present</dt>
          <dd>{formatPresence(detection?.present)}</dd>
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
        The alarm requires uninterrupted drowsiness for the configured duration
        (five seconds by default). Clearing requires continuous awake evidence
        (three seconds by default). Unknown evidence retains the confirmed state
        briefly, then clears any stale alert and marks detection unavailable
        after five seconds, while keeping the latest camera measurements visible.
        Minute counts show historical activity and do not trigger the alarm.
        Missing sensor readings and unoccupied seats do not count. A
        backend-derived sensor drowsy result is counted as drowsy when the camera
        also detects drowsiness or no face is detected; a detected awake face
        overrides the sensor gate. The MQTT indicator reflects this seat’s
        successful alert publication to the broker in the last 10 seconds.
      </p>
      <a className="text-sm underline" href="/calibration">
        Open sensor calibration
      </a>
      {detection?.present === false ? (
        <p className="mt-2 text-sm">Seat unoccupied.</p>
      ) : detection && !detection.face_detected ? (
        <p className="mt-2 text-sm">No face detected in the latest picture.</p>
      ) : null}
    </section>
  )
}
