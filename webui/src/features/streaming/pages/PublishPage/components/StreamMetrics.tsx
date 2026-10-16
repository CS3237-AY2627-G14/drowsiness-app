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
      <p className="mt-4 text-xs text-[var(--sea-ink-soft)]">
        {targetDescription}
        {supersededDescription}
      </p>
    </section>
  )
}
