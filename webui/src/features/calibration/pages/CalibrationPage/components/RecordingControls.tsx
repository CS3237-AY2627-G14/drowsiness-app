import { startRecording, stopRecording } from '#/api/calibration.api'
import type { LabelInterval, Recording } from '../../../types'
import type { useCalibration } from '../hooks/useCalibration'

export const RecordingControls = ({
  calibration,
}: {
  calibration: ReturnType<typeof useCalibration>
}) => {
  const {
    busy,
    live,
    participant,
    setParticipant,
    notes,
    setNotes,
    role,
    setRole,
    run,
    setSelectedId,
    label,
    setLabel,
    posture,
    setPosture,
    mark,
    setMark,
    finishLabel,
    setNotice,
  } = calibration
  return (
    <fieldset
      disabled={busy || !live?.storage_ready}
      className="island-shell space-y-4 rounded-2xl p-5 disabled:opacity-60"
    >
      <legend className="text-xl font-bold">Record and label</legend>
      {!live?.active_recording ? (
        <form
          className="flex flex-wrap gap-3"
          onSubmit={(event) => {
            event.preventDefault()
            void run(async () => {
              const recording = await startRecording({
                participant,
                notes,
                role,
              })
              setSelectedId(recording.id)
            })
          }}
        >
          <label className="grid gap-1 text-sm">
            Participant alias
            <input
              required
              maxLength={100}
              className="rounded border p-2"
              value={participant}
              onChange={(event) => setParticipant(event.target.value)}
            />
          </label>
          <label className="grid gap-1 text-sm">
            Notes
            <input
              maxLength={2000}
              className="rounded border p-2"
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
            />
          </label>
          <label className="grid gap-1 text-sm">
            Recording purpose
            <select
              className="rounded border p-2"
              value={role}
              onChange={(event) =>
                setRole(event.target.value as Recording['role'])
              }
            >
              <option value="development">Development</option>
              <option value="held_out">Reserved final test</option>
            </select>
          </label>
          <button
            className="self-end rounded bg-[var(--sea-ink)] px-4 py-2 text-white"
            type="submit"
          >
            Start recording
          </button>
        </form>
      ) : (
        <>
          <p>
            Recording {live.active_recording.slice(0, 8)}. Transitions remain
            unlabelled.
          </p>
          <div className="flex flex-wrap gap-3">
            <label className="grid gap-1 text-sm">
              Label
              <select
                disabled={mark !== null}
                className="rounded border p-2"
                value={label}
                onChange={(event) =>
                  setLabel(event.target.value as LabelInterval['label'])
                }
              >
                <option value="awake">Awake</option>
                <option value="drowsy">Drowsy posture</option>
                <option value="uncertain">Uncertain</option>
              </select>
            </label>
            <label className="grid gap-1 text-sm">
              Posture
              <input
                disabled={mark !== null}
                className="rounded border p-2"
                value={posture}
                onChange={(event) => setPosture(event.target.value)}
              />
            </label>
            <button
              className="self-end rounded border px-4 py-2"
              disabled={!live.sample || (live.age_seconds ?? 99) > 1}
              onClick={() => {
                if (mark) void run(finishLabel)
                else if (live.sample)
                  setMark({
                    start: live.sample.received_at,
                    end: live.sample.received_at,
                    label,
                    posture,
                  })
              }}
            >
              {mark ? 'Finish label interval' : 'Begin label interval'}
            </button>
            <button
              className="self-end rounded border px-4 py-2"
              onClick={() =>
                void run(async () => {
                  await finishLabel()
                  await stopRecording(live.active_recording!)
                  setNotice('Recording saved.')
                })
              }
            >
              Stop recording
            </button>
          </div>
          {mark && (
            <p role="status">
              Labelling {mark.label}: {mark.posture || 'unspecified posture'}
            </p>
          )}
        </>
      )}
    </fieldset>
  )
}
