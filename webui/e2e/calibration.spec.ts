import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import type {
  LiveTelemetry,
  Recording,
  RecordingDetail,
  TrainingJob,
} from '../src/features/calibration/types'

const installTelemetry = async (page: Page) => {
  await page.addInitScript(() => {
    class TestEventSource {
      onmessage: ((event: { data: string }) => void) | null = null
      onerror: (() => void) | null = null
      timer: ReturnType<typeof setInterval>
      constructor() {
        this.timer = setInterval(() => {
          void fetch('/api/calibration/live')
            .then((response) => response.text())
            .then((data) => this.onmessage?.({ data }))
        }, 100)
      }
      close() {
        clearInterval(this.timer)
      }
    }
    window.EventSource = TestEventSource as unknown as typeof EventSource
  })
}

test('records, corrects labels, trains, activates and restores the baseline', async ({
  page,
}) => {
  await installTelemetry(page)
  const origin = 1_800_000_000
  const live: LiveTelemetry = {
    sample: {
      received_at: origin + 1,
      telemetry: {
        upper_cm: 8,
        lower_mm: 180,
        back_adc: 2400,
        desk_adc: 1500,
        boot_id: 'test',
        sequence: 1,
      },
    },
    age_seconds: 0.1,
    active_recording: null,
    active_model: null,
    candidate_model: null,
    score: null,
    candidate_score: null,
    possible_drowsy: true,
    present: true,
    unavailable_reason: null,
    storage_ready: true,
  }
  const recordings: Recording[] = [0, 1, 2].map((index) => ({
    id: `saved-${index}`,
    participant: `Participant ${index}`,
    notes: '',
    role: 'development',
    started_at: origin - 100,
    stopped_at: origin - 10,
    sample_count: 400,
  }))
  const labels: RecordingDetail['intervals'] = []
  const jobs: TrainingJob[] = []
  await page.route('**/api/calibration/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    const method = route.request().method()
    const json = (body: unknown, status = 200) =>
      route.fulfill({ status, json: body })
    if (path.endsWith('/live')) return json(live)
    if (path.endsWith('/recordings') && method === 'GET')
      return json(recordings)
    if (path.endsWith('/recordings') && method === 'POST') {
      const recording = {
        ...route.request().postDataJSON(),
        id: 'new-recording',
        started_at: origin,
        stopped_at: null,
        sample_count: 0,
      } as Recording
      recordings.push(recording)
      live.active_recording = recording.id
      return json(recording, 201)
    }
    if (path.endsWith('/stop')) {
      const recording = recordings.at(-1)!
      recording.stopped_at = origin + 30
      live.active_recording = null
      return json(recording)
    }
    if (path.endsWith('/labels')) {
      labels.splice(0, labels.length, ...route.request().postDataJSON())
      return route.fulfill({ status: 204 })
    }
    if (path.endsWith('/rehearsal'))
      return json({
        camera_observations: 0,
        awake_minutes: 0,
        comparisons: {},
        note: 'No images stored.',
      })
    if (path.endsWith('/models')) return json(jobs)
    if (path.endsWith('/training')) {
      expect(route.request().postDataJSON().recording_ids).toEqual([
        'saved-0',
        'saved-1',
        'saved-2',
      ])
      const metrics = {
        recall: 1,
        awake_false_positive_rate: 0.1,
        true_positive: 20,
        false_negative: 0,
        false_positive: 2,
        true_negative: 18,
        unavailable: 0,
        samples: 40,
      }
      jobs.push({
        id: 'candidate-model',
        status: 'complete',
        error: null,
        created_at: origin,
        report: {
          selected: 'decision_tree',
          threshold: 0.25,
          coverage: 0.95,
          weak_separation: false,
          validation: { decision_tree: { threshold: 0.25, metrics } },
          baseline: metrics,
          always_positive: { ...metrics, awake_false_positive_rate: 1 },
          held_out: null,
        },
      })
      live.candidate_model = 'candidate-model'
      return json(jobs[0], 202)
    }
    if (path.endsWith('/selection')) {
      live.active_model = route.request().postDataJSON().model_id
      return route.fulfill({ status: 204 })
    }
    const recording = recordings.find((item) => path.endsWith(`/${item.id}`))
    if (recording) return json({ recording, samples: [], intervals: labels })
    return json({ detail: 'Unknown test route' }, 404)
  })
  await page.goto('/calibration')
  await expect(
    page.getByRole('heading', { name: 'Sensor calibration' }),
  ).toBeVisible()
  await page.getByLabel('Participant alias').fill('New participant')
  await page.getByRole('button', { name: 'Start recording' }).click()
  await expect(
    page.getByRole('button', { name: 'Begin label interval' }),
  ).toBeVisible()
  await page.getByRole('button', { name: 'Begin label interval' }).click()
  live.sample!.received_at = origin + 25
  await expect(
    page.getByRole('button', { name: 'Finish label interval' }),
  ).toBeVisible()
  await page.waitForTimeout(200)
  await page.getByRole('button', { name: 'Finish label interval' }).click()
  await expect(page.getByLabel('Interval 1 label')).toBeVisible()
  await page.getByLabel('Interval 1 label').selectOption('uncertain')
  await page.getByRole('button', { name: 'Save labels' }).click()
  await expect.poll(() => labels[0]?.label).toBe('uncertain')
  await page.getByRole('button', { name: 'Stop recording' }).click()
  for (const index of [0, 1, 2])
    await page
      .getByRole('checkbox', {
        name: `Include Participant ${index} saved-${index}`,
      })
      .check()
  await page
    .getByRole('button', { name: 'Train candidate from selected recordings' })
    .click()
  await page.getByRole('button', { name: 'Activate this version' }).click()
  await expect(
    page.getByRole('button', { name: 'Active model', exact: true }),
  ).toBeVisible()
  await page.getByRole('button', { name: 'Restore legacy baseline' }).click()
  await expect.poll(() => live.active_model).toBeNull()
  await page.setViewportSize({ width: 375, height: 812 })
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true)
})

test('explains how to initialize unavailable storage', async ({ page }) => {
  await installTelemetry(page)
  await page.route('**/api/calibration/live', (route) =>
    route.fulfill({ json: { storage_ready: false, sample: null } }),
  )
  await page.goto('/calibration')
  await expect(page.getByRole('alert')).toContainText(
    'Calibration storage is not initialized',
  )
  await expect(
    page.getByRole('button', { name: 'Start recording' }),
  ).toBeDisabled()
})
