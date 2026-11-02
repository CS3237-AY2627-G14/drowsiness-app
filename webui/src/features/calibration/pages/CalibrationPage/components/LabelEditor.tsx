import { useState } from 'react'
import type { LabelInterval, RecordingDetail } from '../../../types'

export const LabelEditor = ({
  detail,
  onSave,
}: {
  detail: RecordingDetail
  onSave: (intervals: LabelInterval[]) => Promise<void>
}) => {
  const [intervals, setIntervals] = useState(() =>
    detail.intervals.map((interval) => ({
      ...interval,
      id: crypto.randomUUID(),
    })),
  )
  const origin = detail.recording.started_at
  const update = (index: number, value: Partial<LabelInterval>) => {
    setIntervals((previous) =>
      previous.map((interval, position) =>
        position === index ? { ...interval, ...value } : interval,
      ),
    )
  }
  return (
    <section className="space-y-3" aria-label="Label editor">
      <h3 className="font-bold">Labels · seconds from recording start</h3>
      <p className="text-sm">
        Correct or remove intervals. Unlabelled and uncertain periods are
        excluded from training.
      </p>
      {intervals.map((interval, index) => (
        <div key={interval.id} className="flex flex-wrap items-center gap-2">
          <input
            aria-label={`Interval ${index + 1} start`}
            type="number"
            min="0"
            step="0.1"
            className="w-24 rounded border p-2"
            value={Number((interval.start - origin).toFixed(1))}
            onChange={(event) => {
              const value = event.currentTarget.valueAsNumber
              if (Number.isFinite(value))
                update(index, { start: origin + value })
            }}
          />
          <input
            aria-label={`Interval ${index + 1} end`}
            type="number"
            min="0"
            step="0.1"
            className="w-24 rounded border p-2"
            value={Number((interval.end - origin).toFixed(1))}
            onChange={(event) => {
              const value = event.currentTarget.valueAsNumber
              if (Number.isFinite(value)) update(index, { end: origin + value })
            }}
          />
          <select
            aria-label={`Interval ${index + 1} label`}
            className="rounded border p-2"
            value={interval.label}
            onChange={(event) =>
              update(index, {
                label: event.target.value as LabelInterval['label'],
              })
            }
          >
            <option value="awake">Awake</option>
            <option value="drowsy">Drowsy posture</option>
            <option value="uncertain">Uncertain</option>
          </select>
          <input
            aria-label={`Interval ${index + 1} posture`}
            className="rounded border p-2"
            placeholder="Posture"
            value={interval.posture}
            onChange={(event) => update(index, { posture: event.target.value })}
          />
          <button
            className="underline"
            onClick={() =>
              setIntervals((previous) =>
                previous.filter((_, position) => position !== index),
              )
            }
          >
            Remove
          </button>
        </div>
      ))}
      <div className="flex gap-4">
        <button
          className="underline"
          onClick={() =>
            setIntervals((previous) => [
              ...previous,
              {
                id: crypto.randomUUID(),
                start: origin,
                end: origin + 1,
                label: 'uncertain',
                posture: '',
              },
            ])
          }
        >
          Add interval
        </button>
        <button
          className="rounded bg-[var(--sea-ink)] px-4 py-2 text-white"
          onClick={() =>
            void onSave(
              intervals.map(({ start, end, label, posture }) => ({
                start,
                end,
                label,
                posture,
              })),
            )
          }
        >
          Save labels
        </button>
      </div>
    </section>
  )
}
