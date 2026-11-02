import type { RawSample } from '../../../types'

export const SensorChart = ({
  history,
  field,
  label,
}: {
  history: RawSample[]
  field: keyof Pick<
    RawSample['telemetry'],
    'upper_cm' | 'lower_mm' | 'back_adc' | 'desk_adc'
  >
  label: string
}) => {
  const values = history.map((sample) => sample.telemetry[field])
  const valid = values.filter((value): value is number => value !== null)
  const low = Math.min(...valid, 0)
  const high = Math.max(...valid, low + 1)
  const points = values.map((value, index) =>
    value === null
      ? null
      : `${(index / Math.max(values.length - 1, 1)) * 300},${75 - ((value - low) / (high - low)) * 65}`,
  )
  const segments: string[] = []
  let segment: string[] = []
  for (const point of points) {
    if (point === null) {
      if (segment.length) segments.push(segment.join(' '))
      segment = []
    } else segment.push(point)
  }
  if (segment.length) segments.push(segment.join(' '))
  return (
    <figure className="island-shell rounded-2xl p-4">
      <figcaption className="flex justify-between gap-3 text-sm">
        <span>{label}</span>
        <strong>{values.at(-1) ?? 'Unavailable'}</strong>
      </figcaption>
      <svg
        viewBox="0 0 300 85"
        role="img"
        aria-label={`${label} recent readings`}
        className="mt-3 w-full"
      >
        {segments.map((line, index) => (
          <polyline
            key={index}
            points={line}
            fill="none"
            stroke="var(--lagoon-deep)"
            strokeWidth="2"
          />
        ))}
      </svg>
      <p className="text-xs opacity-70">
        Recent readings · scale {low}–{high}
      </p>
    </figure>
  )
}
