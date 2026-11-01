import type { Metrics, TrainingJob } from '../../../types'

const percent = (value: number | null) =>
  value === null ? '—' : `${(value * 100).toFixed(1)}%`

export const MetricsTable = ({ rows }: { rows: Record<string, Metrics> }) => (
  <div className="overflow-x-auto">
    <table className="w-full text-left text-sm">
      <thead>
        <tr>
          <th className="p-2">Evaluation</th>
          <th>Recall</th>
          <th>Awake false positives</th>
          <th>TP / FN / FP / TN</th>
          <th>Unavailable</th>
        </tr>
      </thead>
      <tbody>
        {Object.entries(rows).map(([name, metrics]) => (
          <tr key={name} className="border-t">
            <td className="p-2">{name}</td>
            <td>{percent(metrics.recall)}</td>
            <td>{percent(metrics.awake_false_positive_rate)}</td>
            <td>
              {metrics.true_positive} / {metrics.false_negative} /{' '}
              {metrics.false_positive} / {metrics.true_negative}
            </td>
            <td>{metrics.unavailable}</td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
)

export const ModelReport = ({
  job,
  active,
  onActivate,
}: {
  job: TrainingJob
  active: boolean
  onActivate: () => void
}) => (
  <article className="island-shell space-y-3 rounded-2xl p-5">
    <h3 className="font-bold">
      {job.id.slice(0, 8)} · {job.status}
      {active ? ' · Active' : ''}
    </h3>
    {job.error && <p role="alert">{job.error}</p>}
    {job.report && (
      <>
        <p className="text-sm">
          {job.report.selected} · threshold {job.report.threshold.toFixed(3)} ·
          valid-window coverage {percent(job.report.coverage)}
        </p>
        {job.report.weak_separation && (
          <p className="font-semibold text-amber-800">
            Weak separation: many awake postures also pass the sensor gate.
            Review face-loss false alerts before activation.
          </p>
        )}
        <MetricsTable
          rows={{
            ...Object.fromEntries(
              Object.entries(job.report.validation).map(([name, result]) => [
                `Validation: ${name}`,
                result.metrics,
              ]),
            ),
            'Legacy baseline': job.report.baseline,
            'Always possible drowsy': job.report.always_positive,
          }}
        />
        {job.report.held_out ? (
          <>
            <h4 className="font-semibold">Reserved recording results</h4>
            <MetricsTable
              rows={{
                Overall: job.report.held_out.metrics,
                ...job.report.held_out.by_posture,
              }}
            />
          </>
        ) : (
          <p className="text-sm">No reserved recording evaluated.</p>
        )}
        <button
          disabled={active}
          className="rounded border px-4 py-2 disabled:opacity-50"
          onClick={onActivate}
        >
          {active ? 'Active model' : 'Activate this version'}
        </button>
      </>
    )}
  </article>
)
