import { Link } from '@tanstack/react-router'
import { saveLabels, selectModel, trainModel } from '#/api/calibration.api'
import { useCalibration } from './hooks/useCalibration'
import { TelemetryPanel } from './components/TelemetryPanel'
import { LabelEditor } from './components/LabelEditor'
import { ModelReport } from './components/ModelReport'
import { RehearsalReport } from './components/RehearsalReport'
import { RecordingControls } from './components/RecordingControls'

export const CalibrationPage = () => {
  const calibration = useCalibration()
  const {
    live,
    history,
    connected,
    recordings,
    models,
    setSelectedId,
    rehearsal,
    detail,
    selected,
    setSelected,
    selectedIds,
    busy,
    error,
    notice,
    setNotice,
    run,
  } = calibration
  return (
    <main className="mx-auto max-w-6xl space-y-7 p-5 sm:p-10">
      <header className="space-y-2">
        <Link to="/streaming" className="text-sm underline">
          ← Camera monitoring
        </Link>
        <p className="text-sm font-semibold uppercase tracking-widest">
          Student 1 · Seat 1
        </p>
        <h1 className="text-3xl font-bold">Sensor calibration</h1>
        <p>
          Record staged postures, correct labels, and compare model versions
          before activation. Recordings stay available for future recalibration.
        </p>
      </header>
      {!connected && <p role="status">Connecting to telemetry…</p>}
      {live && !live.storage_ready && (
        <p role="alert" className="rounded border p-4">
          Calibration storage is not initialized. From api/:{' '}
          <code>uv run python -m modules.processing.calibration init</code>,
          then restart the API.
        </p>
      )}
      {error && (
        <p role="alert" className="rounded border border-red-500 p-3">
          {error}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      <TelemetryPanel live={live} history={history} />
      <RecordingControls calibration={calibration} />
      <section className="island-shell space-y-4 rounded-2xl p-5">
        <h2 className="text-xl font-bold">Saved recordings</h2>
        {recordings.error && (
          <p role="alert">
            Could not load recordings: {recordings.error.message}
          </p>
        )}
        {!recordings.data?.length && <p>No recordings yet.</p>}
        {recordings.data?.map((recording) => (
          <div
            key={recording.id}
            className="flex flex-wrap items-center gap-3 border-b py-3"
          >
            <input
              type="checkbox"
              aria-label={`Include ${recording.participant} ${recording.id.slice(0, 8)}`}
              disabled={!recording.stopped_at}
              checked={selectedIds.has(recording.id)}
              onChange={(event) =>
                setSelected((previous) =>
                  event.target.checked
                    ? [...previous, recording.id]
                    : previous.filter((id) => id !== recording.id),
                )
              }
            />
            <button
              className="underline"
              onClick={() => setSelectedId(recording.id)}
            >
              {recording.participant} · {recording.id.slice(0, 8)}
            </button>
            <span className="text-sm">
              {recording.role} · {recording.sample_count} readings ·{' '}
              {recording.stopped_at ? 'Saved' : 'Recording'}
            </span>
            <a
              className="ml-auto text-sm underline"
              href={`/api/calibration/recordings/${recording.id}/export`}
            >
              Export CSV
            </a>
          </div>
        ))}
        <button
          disabled={
            busy ||
            selected.length < 3 ||
            models.data?.some((job) => job.status === 'running')
          }
          className="rounded border px-4 py-2 disabled:opacity-50"
          onClick={() =>
            void run(async () => {
              await trainModel(selected)
              setNotice(
                'Training started. Monitoring continues with the active model.',
              )
            })
          }
        >
          Train candidate from selected recordings
        </button>
        <p className="text-sm">
          Select at least three development recordings containing both classes.
          Include a reserved recording only for final evaluation after
          development.
        </p>
        {detail.isLoading && <p>Loading recording…</p>}
        {detail.error && <p role="alert">{detail.error.message}</p>}
        {rehearsal.data && <RehearsalReport report={rehearsal.data} />}
        {detail.data && (
          <LabelEditor
            key={`${detail.data.recording.id}:${JSON.stringify(detail.data.intervals)}`}
            detail={detail.data}
            onSave={(intervals) =>
              run(async () => {
                await saveLabels(detail.data.recording.id, intervals)
                setNotice(
                  'Labels saved. Existing model versions are unchanged.',
                )
              })
            }
          />
        )}
      </section>
      <section className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-xl font-bold">Model versions</h2>
          <button
            disabled={busy || !live?.active_model}
            className="rounded border px-4 py-2 disabled:opacity-50"
            onClick={() =>
              void run(async () => {
                await selectModel(null)
                setNotice(
                  'Legacy baseline restored; observation history reset.',
                )
              })
            }
          >
            Restore legacy baseline
          </button>
        </div>
        {models.error && (
          <p role="alert">Could not load models: {models.error.message}</p>
        )}
        {models.data?.map((job) => (
          <ModelReport
            key={job.id}
            job={job}
            active={job.id === live?.active_model}
            onActivate={() =>
              void run(async () => {
                await selectModel(job.id)
                setNotice('Model activated; observation history reset.')
              })
            }
          />
        ))}
        <p className="text-sm">
          Activation is explicit. Older versions remain available for rollback.
          Sensor scores are not calibrated confidence percentages;
          staged-posture tests do not establish physiological drowsiness
          accuracy.
        </p>
      </section>
    </main>
  )
}
