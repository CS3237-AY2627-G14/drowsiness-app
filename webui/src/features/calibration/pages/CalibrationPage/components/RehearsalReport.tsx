import type { Rehearsal } from '../../../types'

export const RehearsalReport = ({ report }: { report: Rehearsal }) => (
  <section className="space-y-3">
    <h3 className="font-bold">Camera rehearsal comparison</h3>
    <p className="text-sm">
      {report.camera_observations} camera observations ·{' '}
      {report.awake_minutes.toFixed(1)} labelled awake minutes. Candidates
      cannot trigger hardware alerts.
    </p>
    {report.camera_observations > 0 && (
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr>
              <th className="p-2">Gate</th>
              <th>Valid observations</th>
              <th>False alert activations</th>
              <th>Per awake minute</th>
              <th>Alert latency per drowsy episode (s)</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(report.comparisons).map(([name, result]) => (
              <tr key={name} className="border-t">
                <td className="p-2">{name}</td>
                <td>{result.valid_observations}</td>
                <td>{result.false_alert_activations}</td>
                <td>
                  {result.false_alerts_per_awake_minute?.toFixed(2) ?? '—'}
                </td>
                <td>
                  {result.alert_latency_seconds_by_drowsy_episode
                    .map((latency) => latency?.toFixed(1) ?? 'No new alert')
                    .join(', ') || '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )}
    <p className="text-xs opacity-70">{report.note}</p>
  </section>
)
