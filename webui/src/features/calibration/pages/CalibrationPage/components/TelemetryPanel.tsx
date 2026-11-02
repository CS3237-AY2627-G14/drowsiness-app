import type { LiveTelemetry, RawSample } from '../../../types'
import { SensorChart } from './SensorChart'

export const TelemetryPanel = ({
  live,
  history,
}: {
  live: LiveTelemetry | null
  history: RawSample[]
}) => {
  const sensorState =
    live?.possible_drowsy == null
      ? 'Unavailable'
      : live.possible_drowsy
        ? 'Possible drowsy'
        : 'Awake'
  return (
    <section aria-label="Live telemetry" className="space-y-3">
      <div className="island-shell flex flex-wrap gap-5 rounded-2xl p-4 text-sm">
        <span>
          Presence:{' '}
          <strong>
            {live?.present == null
              ? 'Unknown'
              : live.present
                ? 'Occupied'
                : 'Unoccupied'}
          </strong>
        </span>
        <span>
          Age: <strong>{live?.age_seconds?.toFixed(1) ?? '—'} s</strong>
        </span>
        <span>
          Sensor: <strong>{sensorState}</strong>
        </span>
        <span>
          Active score: <strong>{live?.score?.toFixed(3) ?? '—'}</strong>
        </span>
        <span>
          Candidate score:{' '}
          <strong>{live?.candidate_score?.toFixed(3) ?? '—'}</strong>
        </span>
        <span>
          Model:{' '}
          <strong>
            {live?.active_model?.slice(0, 8) ?? 'Legacy baseline'}
          </strong>
        </span>
      </div>
      {live?.unavailable_reason && (
        <p className="text-sm">
          Status: {live.unavailable_reason.replaceAll('_', ' ')}
        </p>
      )}
      <div className="grid gap-4 sm:grid-cols-2">
        <SensorChart
          history={history}
          field="upper_cm"
          label="Upper distance (cm)"
        />
        <SensorChart
          history={history}
          field="lower_mm"
          label="Lower distance (mm)"
        />
        <SensorChart
          history={history}
          field="back_adc"
          label="Backrest pressure (ADC)"
        />
        <SensorChart
          history={history}
          field="desk_adc"
          label="Desk pressure (ADC)"
        />
      </div>
    </section>
  )
}
