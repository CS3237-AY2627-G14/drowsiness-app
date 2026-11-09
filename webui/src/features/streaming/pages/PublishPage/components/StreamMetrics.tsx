import type { StreamMetricsProps } from '../PublishPage.types'
import { videoConfig } from '#/lib/config'

export const StreamMetrics = ({ metrics }: StreamMetricsProps) => {
  const resultAge =
    metrics?.resultAgeMs != null
      ? (metrics.resultAgeMs / 1000).toFixed(1) + ' s'
      : '—'
  const metricItems = [
    {
      label: 'Received',
      value: metrics ? metrics.received_fps.toFixed(1) + ' fps' : '—',
    },
    {
      label: 'Processed',
      value: metrics ? metrics.processed_fps.toFixed(1) + ' fps' : '—',
    },
    {
      label: 'Upload',
      value: metrics ? metrics.upload_kbps.toFixed(0) + ' kbps' : '—',
    },
    { label: 'Result age', value: resultAge },
  ]
  const debug = metrics?.detection_state
  const seconds = (value: number | null | undefined) =>
    value == null ? '—' : `${value.toFixed(1)} s`
  const debugItems = debug
    ? [
        ['Confirmed state', debug.confirmed_state],
        ['Transition', debug.phase.replaceAll('_', ' ')],
        [
          'Current classification',
          debug.current_drowsy === null
            ? 'Unknown'
            : debug.current_drowsy
              ? 'Drowsy'
              : 'Awake',
        ],
        [
          'Entry evidence',
          `${seconds(debug.drowsy_seconds)} / ${debug.entry_required_seconds} s`,
        ],
        [
          'Recovery evidence',
          `${seconds(debug.awake_seconds)} / ${debug.recovery_required_seconds} s`,
        ],
        [
          'Unknown duration',
          `${seconds(debug.unknown_seconds)} / ${debug.unknown_timeout_seconds} s`,
        ],
        ['Camera age', seconds(debug.camera_age_seconds)],
        ['Sensor evidence age', seconds(debug.sensor_age_seconds)],
        ['Unavailable reason', debug.reason?.replaceAll('_', ' ') ?? 'None'],
        ['Pending frames', String(metrics.pending_frames)],
        ['Inference in flight', metrics.in_flight ? 'Yes' : 'No'],
        [
          'Processed / replaced / stale',
          `${metrics.processed_frames} / ${metrics.replaced_frames} / ${metrics.stale_frames}`,
        ],
      ]
    : []
  const targetDescription = `Target: ${videoConfig.width} × ${videoConfig.height}, up to ${videoConfig.frameRate} fps.`
  const supersededDescription = metrics
    ? ` Superseded frames: ${metrics.replaced_frames + metrics.stale_frames}.`
    : ''
  return (
    <section
      className="island-shell rounded-2xl p-4 sm:p-6"
      aria-label="Streaming statistics"
    >
      <h2 className="mb-4 text-lg font-semibold">Frame processing</h2>
      <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {metricItems.map(({ label, value }) => (
          <div key={label} className="rounded-xl bg-white/70 p-2.5 sm:p-4">
            <dt className="text-xs text-[var(--sea-ink-soft)]">{label}</dt>
            <dd className="mt-1.5 text-sm font-bold tabular-nums sm:text-lg">
              {value}
            </dd>
          </div>
        ))}
      </dl>
      {debug ? (
        <details className="mt-4">
          <summary className="cursor-pointer font-medium">
            Detection debugging
          </summary>
          <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
            {debugItems.map(([label, value]) => (
              <div key={label}>
                <dt className="text-[var(--sea-ink-soft)]">{label}</dt>
                <dd className="tabular-nums">{value}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-3 text-xs text-[var(--sea-ink-soft)]">
            Live server snapshot. Evidence can reset before a transition
            completes. Unknown evidence temporarily retains the confirmed state.
          </p>
        </details>
      ) : null}
      <p className="mt-4 text-xs text-[var(--sea-ink-soft)]">
        {targetDescription}
        {supersededDescription}
      </p>
    </section>
  )
}
