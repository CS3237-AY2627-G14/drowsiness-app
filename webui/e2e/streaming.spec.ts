import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

const startCameraPreview = async (
  page: Page,
  url = '/streaming',
): Promise<void> => {
  await page.goto(url)
  await expect(page.getByLabel('Seat', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Start camera' }).click()
  await expect(page.getByRole('status')).toHaveText('Preview ready')
}

const setDemoPublishToken = async (
  page: Page,
  token: string,
): Promise<void> => {
  await page.getByText('Demo credentials', { exact: true }).click()
  await page.getByLabel('Session token').fill(token)
}

const expectLiveCameraPreview = async (page: Page): Promise<void> => {
  const preview = page.getByLabel('Camera preview', { exact: true })
  await expect
    .poll(() =>
      preview.evaluate((element) => {
        const video = element as HTMLVideoElement
        const stream = video.srcObject as MediaStream | null
        const track = stream?.getVideoTracks()[0]
        return !video.paused && track?.readyState === 'live'
      }),
    )
    .toBe(true)
  await expect(
    page.getByRole('button', { name: 'Start camera' }),
  ).toBeDisabled()
  await expect(
    page.getByRole('button', { name: 'Publish', exact: true }),
  ).toBeEnabled()
}

test('static routes support redirects, refresh, mobile layout, and missing pages', async ({
  page,
}) => {
  await page.goto('/')
  await expect(page).toHaveURL(/\/streaming$/)
  await expect(
    page.getByLabel('Seat', { exact: true }).locator('option'),
  ).toHaveCount(10)
  await page.reload()
  await expect(
    page.getByRole('heading', { name: 'Classroom camera' }),
  ).toBeVisible()
  await page.setViewportSize({ width: 375, height: 812 })
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true)
  await page.goto('/missing')
  await expect(
    page.getByRole('heading', { name: 'Page not found' }),
  ).toBeVisible()
})

test('sends full-frame JPEGs for real detection and stops the camera', async ({
  page,
}) => {
  await startCameraPreview(page)
  await page.getByRole('button', { name: 'Publish', exact: true }).click()
  await expect(page.getByRole('status')).toHaveText('Live', { timeout: 25_000 })
  await expect(page.getByText(/Target: 1280 × 720/)).toBeVisible()
  await expect(page.getByText(/^[\d.]+ fps$/).first()).toBeVisible()
  await expect(page.getByText(/^\d+ kbps$/)).toBeVisible()
  expect(
    await page
      .locator('video')
      .evaluate(
        (video) =>
          (
            (video as HTMLVideoElement).srcObject as MediaStream
          ).getVideoTracks()[0]?.readyState,
      ),
  ).toBe('live')
  await page.getByRole('button', { name: 'Stop', exact: true }).click()
  await expect(page.getByRole('status')).toHaveText('Camera off')
  expect(
    await page
      .locator('video')
      .evaluate((video) => (video as HTMLVideoElement).srcObject),
  ).toBeNull()
})

test('rejects an invalid token and retries publishing with the same camera', async ({
  page,
}) => {
  await startCameraPreview(page)
  await setDemoPublishToken(page, 'invalid-token')
  await page.getByRole('button', { name: 'Publish', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('not authorized')
  await expect(page.getByRole('status')).toHaveText('Publishing stopped')
  const cameraHandle = await page
    .locator('video')
    .evaluateHandle((video) => (video as HTMLVideoElement).srcObject)
  await page.getByLabel('Session token').fill('demo-room-101-seat-1')
  await expectLiveCameraPreview(page)
  await page.getByRole('button', { name: 'Publish', exact: true }).click()
  await expect(page.getByRole('status')).toHaveText('Live', { timeout: 25_000 })
  const hasSameCamera = await page
    .locator('video')
    .evaluate(
      (video, camera) => (video as HTMLVideoElement).srcObject === camera,
      cameraHandle,
    )
  expect(hasSameCamera).toBe(true)
  await cameraHandle.dispose()
  await page.getByRole('button', { name: 'Stop', exact: true }).click()
  await expect(page.getByRole('status')).toHaveText('Camera off')
})

test('rejects a token belonging to another seat', async ({ page }) => {
  await startCameraPreview(page, '/streaming?room=101&seat=2')
  await setDemoPublishToken(page, 'demo-room-101-seat-1')
  await page.getByRole('button', { name: 'Publish', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('not authorized')
  await expect(page.getByRole('status')).toHaveText('Publishing stopped')
})

test('shows a useful error for denied camera permission', async ({ page }) => {
  await page.addInitScript(() => {
    navigator.mediaDevices.getUserMedia = () =>
      Promise.reject(new DOMException('Denied', 'NotAllowedError'))
  })
  await page.goto('/streaming')
  await page.getByRole('button', { name: 'Start camera' }).click()
  await expect(page.getByRole('alert')).toContainText(
    'Camera permission was denied',
  )
})

test('shows a useful error when no camera is available', async ({ page }) => {
  await page.addInitScript(() => {
    navigator.mediaDevices.getUserMedia = () =>
      Promise.reject(new DOMException('Missing', 'NotFoundError'))
  })
  await page.goto('/streaming')
  await page.getByRole('button', { name: 'Start camera' }).click()
  await expect(page.getByRole('alert')).toContainText('No camera was found')
})

test('preserves all four edges of a portrait camera frame', async ({
  page,
}) => {
  await page.addInitScript(() => {
    navigator.mediaDevices.getUserMedia = () => {
      const source = document.createElement('canvas')
      source.width = 480
      source.height = 640
      const context = source.getContext('2d')!
      context.fillStyle = 'white'
      context.fillRect(0, 0, 480, 640)
      for (const [color, x, y, width, height] of [
        ['red', 0, 0, 16, 640],
        ['yellow', 464, 0, 16, 640],
        ['lime', 0, 0, 480, 16],
        ['blue', 0, 624, 480, 16],
      ] as const) {
        context.fillStyle = color
        context.fillRect(x, y, width, height)
      }
      return Promise.resolve(source.captureStream(15))
    }
  })
  await startCameraPreview(page)
  const colors = await page.locator('canvas').evaluate((element) => {
    const canvas = element as HTMLCanvasElement
    const context = canvas.getContext('2d')!
    return [
      [379, 360],
      [901, 360],
      [640, 9],
      [640, 711],
      [10, 360],
    ].map(([x, y]) =>
      Array.from(context.getImageData(x!, y!, 1, 1).data).slice(0, 3),
    )
  })
  const expected = [
    [255, 0, 0],
    [255, 255, 0],
    [0, 255, 0],
    [0, 0, 255],
    [16, 29, 34],
  ]
  // Browser video color conversion can change a channel by a few levels.
  for (const [index, color] of colors.entries()) {
    for (const [channel, value] of color.entries()) {
      expect(Math.abs(value - expected[index]![channel]!)).toBeLessThanOrEqual(
        3,
      )
    }
  }
  await page.getByRole('button', { name: 'Stop', exact: true }).click()
})

test('keeps the camera preview when the Socket.IO connection fails', async ({
  page,
}) => {
  await page.routeWebSocket('**/api/socket.io/**', (socket) => {
    socket.close({ code: 1011, reason: 'Unavailable' })
  })
  await startCameraPreview(page)
  await page.getByRole('button', { name: 'Publish', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText(
    /Cannot reach the streaming service|timed out/,
    { timeout: 10_000 },
  )
  await expect(page.getByRole('status')).toHaveText('Publishing stopped')
  await expectLiveCameraPreview(page)
})

test('keeps a restarted preview when the cancelled camera request finishes late', async ({
  page,
}) => {
  await page.addInitScript(() => {
    const getUserMedia = navigator.mediaDevices.getUserMedia.bind(
      navigator.mediaDevices,
    )
    let firstRequest = true
    navigator.mediaDevices.getUserMedia = async (constraints) => {
      const delay = firstRequest
      firstRequest = false
      const stream = await getUserMedia(constraints)
      if (delay) {
        Object.assign(window, { lateStream: stream })
        await new Promise((resolve) => setTimeout(resolve, 1500))
      }
      return stream
    }
  })
  await page.route('**/api/classrooms', (route) =>
    route.fulfill({
      json: [
        {
          id: 101,
          name: 'Room 101',
          seats: [{ id: 1, room_id: 101, seat_number: 1 }],
        },
      ],
    }),
  )
  await page.goto('/streaming')
  await page.getByRole('button', { name: 'Start camera' }).click()
  await expect(
    page.getByRole('button', { name: 'Stop', exact: true }),
  ).toBeEnabled()
  await page.getByRole('button', { name: 'Stop', exact: true }).click()
  await expect(page.getByRole('status')).toHaveText('Camera off')
  await page.getByRole('button', { name: 'Start camera' }).click()
  await expect(page.getByRole('status')).toHaveText('Preview ready')
  await expect
    .poll(() =>
      page.evaluate(() => {
        const stream = (window as Window & { lateStream?: MediaStream })
          .lateStream
        return (
          stream?.getTracks().every((track) => track.readyState === 'ended') ??
          false
        )
      }),
    )
    .toBe(true)
  await expect(page.getByRole('status')).toHaveText('Preview ready')
  expect(
    await page
      .locator('video')
      .evaluate(
        (video) =>
          (video as HTMLVideoElement).srcObject instanceof MediaStream &&
          (
            (video as HTMLVideoElement).srcObject as MediaStream
          ).getVideoTracks()[0]?.readyState,
      ),
  ).toBe('live')
  await page.getByRole('button', { name: 'Stop', exact: true }).click()
})

test('offers a retry when the classroom API is unavailable', async ({
  page,
}) => {
  await page.route('**/api/classrooms', (route) =>
    route.fulfill({ status: 503 }),
  )
  await page.goto('/streaming')
  await expect(page.getByRole('alert')).toContainText(
    'Could not load classrooms',
  )
  await expect(
    page.getByRole('button', { name: 'Retry classrooms' }),
  ).toBeEnabled()
})

test('allows choosing a populated classroom when the first one is empty', async ({
  page,
}) => {
  await page.route('**/api/classrooms', (route) =>
    route.fulfill({
      json: [
        { id: 100, name: 'Empty classroom', seats: [] },
        {
          id: 101,
          name: 'Room 101',
          seats: [{ id: 1, room_id: 101, seat_number: 1 }],
        },
      ],
    }),
  )
  await page.goto('/streaming')
  await expect(page.getByLabel('Seat', { exact: true })).toBeDisabled()
  await expect(
    page.getByRole('button', { name: 'Start camera' }),
  ).toBeDisabled()
  await page.getByLabel('Room', { exact: true }).selectOption('101')
  await expect(page.getByLabel('Seat', { exact: true })).toBeEnabled()
  await expect(page.getByRole('button', { name: 'Start camera' })).toBeEnabled()
})

test('retains the existing publisher and releases its seat on navigation', async ({
  page,
  context,
}) => {
  await startCameraPreview(page, '/streaming?room=101&seat=3')
  await page.getByRole('button', { name: 'Publish', exact: true }).click()
  await expect(page.getByRole('status')).toHaveText('Live', { timeout: 25_000 })
  const second = await context.newPage()
  await startCameraPreview(second, '/streaming?room=101&seat=3')
  await second.getByRole('button', { name: 'Publish', exact: true }).click()
  await expect(second.getByRole('alert')).toContainText(
    'already has an active publisher',
  )
  await expect(page.getByRole('status')).toHaveText('Live')
  await page.goto('/missing')
  await expect(
    page.getByRole('heading', { name: 'Page not found' }),
  ).toBeVisible()
  await expectLiveCameraPreview(second)
  await second.getByRole('button', { name: 'Publish', exact: true }).click()
  await expect(second.getByRole('status')).toHaveText('Live', {
    timeout: 25_000,
  })
  await second.getByRole('button', { name: 'Stop', exact: true }).click()
  await second.close()
})

test('keeps the camera after a connection drops and allows republishing', async ({
  page,
}) => {
  let disconnect = async (): Promise<void> => {
    throw new Error('No publisher connected')
  }
  await page.routeWebSocket('**/api/socket.io/**', (socket) => {
    const server = socket.connectToServer()
    disconnect = async () => {
      await Promise.all([
        socket.close({ code: 1011, reason: 'Connection interrupted' }),
        server.close(),
      ])
    }
  })
  await startCameraPreview(page)
  await page.getByRole('button', { name: 'Publish', exact: true }).click()
  await expect(page.getByRole('status')).toHaveText('Live')
  await disconnect()
  await expect(page.getByRole('status')).toHaveText('Publishing stopped')
  await expect(page.getByRole('alert')).toContainText(
    'Cannot reach the streaming service',
  )
  await expectLiveCameraPreview(page)
  await page.getByRole('button', { name: 'Publish', exact: true }).click()
  await expect(page.getByRole('status')).toHaveText('Live')
  await page.getByRole('button', { name: 'Stop', exact: true }).click()
  await expect(page.getByRole('status')).toHaveText('Camera off')
})

test('keeps room and seat in the URL across refresh and back navigation', async ({
  page,
}) => {
  await page.route('**/api/classrooms', (route) =>
    route.fulfill({
      json: [
        {
          id: 101,
          name: 'Room 101',
          seats: [{ id: 1, room_id: 101, seat_number: 1 }],
        },
        {
          id: 102,
          name: 'Room 102',
          seats: [
            { id: 11, room_id: 102, seat_number: 1 },
            { id: 12, room_id: 102, seat_number: 2 },
          ],
        },
      ],
    }),
  )
  await page.goto('/streaming?room=102&seat=12')
  await expect(page.getByLabel('Room', { exact: true })).toHaveValue('102')
  await expect(page.getByLabel('Seat', { exact: true })).toHaveValue('12')
  await page.reload()
  await expect(page.getByLabel('Seat', { exact: true })).toHaveValue('12')
  await page.getByLabel('Room', { exact: true }).selectOption('101')
  await expect(page).toHaveURL(/room=101/)
  await expect(page.getByLabel('Seat', { exact: true })).toHaveValue('1')
  await page.goBack()
  await expect(page.getByLabel('Room', { exact: true })).toHaveValue('102')
  await expect(page.getByLabel('Seat', { exact: true })).toHaveValue('12')
  await page.getByLabel('Seat', { exact: true }).selectOption('11')
  await expect(page).toHaveURL(/seat=11/)
  await expect(page.getByRole('status')).toHaveText('Camera off')
  await page.getByRole('button', { name: 'Start camera' }).click()
  await expect(page.getByRole('status')).toHaveText('Preview ready')
})

test('falls back safely for invalid room and seat query parameters', async ({
  page,
}) => {
  await page.goto('/streaming?room=bad&seat=-2')
  await expect(page.getByLabel('Room', { exact: true })).toHaveValue('101')
  await expect(page.getByLabel('Seat', { exact: true })).toHaveValue('1')
})

test('stops publishing when the camera is interrupted and allows a fresh start', async ({
  page,
}) => {
  await startCameraPreview(page)
  await page.getByRole('button', { name: 'Publish', exact: true }).click()
  await expect(page.getByRole('status')).toHaveText('Live')
  await page.locator('video').evaluate((video) => {
    const stream = (video as HTMLVideoElement).srcObject as MediaStream
    const cameraEnded = new Event('ended')
    const track = stream.getVideoTracks()[0]
    track?.dispatchEvent(cameraEnded)
  })
  await expect(page.getByRole('alert')).toContainText('camera was interrupted')
  await expect(page.getByRole('status')).toHaveText('Camera unavailable')
  expect(
    await page
      .locator('video')
      .evaluate((video) => (video as HTMLVideoElement).srcObject),
  ).toBeNull()
  await page.getByRole('button', { name: 'Start camera' }).click()
  await expect(page.getByRole('status')).toHaveText('Preview ready')
  await page.getByRole('button', { name: 'Publish', exact: true }).click()
  await expect(page.getByRole('status')).toHaveText('Live')
  await page.getByRole('button', { name: 'Stop', exact: true }).click()
})

test('stops publishing after an encoding failure and keeps the camera preview', async ({
  page,
}) => {
  await startCameraPreview(page)
  await page.getByRole('button', { name: 'Publish', exact: true }).click()
  await expect(page.getByRole('status')).toHaveText('Live')
  await page.locator('canvas').evaluate((canvas) => {
    ;(canvas as HTMLCanvasElement).toBlob = (callback) => callback(null)
  })
  await expect(page.getByRole('alert')).toContainText('could not encode a JPEG')
  await expect(page.getByRole('status')).toHaveText('Publishing stopped')
  await expectLiveCameraPreview(page)
  await page.getByRole('button', { name: 'Stop', exact: true }).click()
  await expect(page.getByRole('status')).toHaveText('Camera off')
})

test('cancels pending authentication without a late timeout affecting the restarted camera', async ({
  page,
}) => {
  await page.routeWebSocket('**/api/socket.io/**', () => {})
  await startCameraPreview(page)
  await page.getByRole('button', { name: 'Publish', exact: true }).click()
  await expect(page.getByRole('status')).toHaveText('Connecting')
  await page.getByRole('button', { name: 'Stop', exact: true }).click()
  await expect(page.getByRole('status')).toHaveText('Camera off')
  await page.getByRole('button', { name: 'Start camera' }).click()
  await expect(page.getByRole('status')).toHaveText('Preview ready')
  await page.waitForTimeout(5500)
  await expect(page.getByRole('alert')).toHaveCount(0)
  await expect(page.getByRole('status')).toHaveText('Preview ready')
  await page.getByRole('button', { name: 'Stop', exact: true }).click()
})

test('keeps credential overrides out of the URL and resets them on refresh', async ({
  page,
}) => {
  await page.goto('/streaming?room=101&seat=2')
  await expect(page.getByLabel('Seat', { exact: true })).toHaveValue('2')
  await setDemoPublishToken(page, 'private-test-override')
  await expect(page).toHaveURL(/room=101&seat=2$/)
  await page.reload()
  await page.getByText('Demo credentials', { exact: true }).click()
  await expect(page.getByLabel('Session token')).toHaveValue(
    'demo-room-101-seat-2',
  )
})

test('shows minute counts, updates the alert, and clears the summary on restart', async ({
  page,
}) => {
  let drowsyPictures = 22
  await page.routeWebSocket('**/api/socket.io/**', (socket) => {
    const server = socket.connectToServer()
    server.onMessage((message) => {
      if (typeof message !== 'string' || !message.startsWith('42["status",')) {
        socket.send(message)
        return
      }
      const packet = JSON.parse(message.slice(2)) as [
        string,
        Record<string, unknown>,
      ]
      packet[1].detection = {
        captured_at_ms: 0,
        ear: 0.1,
        fatigue_probability: 0.9,
        minute: {
          valid_samples: 42,
          drowsy_samples: drowsyPictures,
          unavailable_samples: 18,
          window_seconds: 60,
        },
        alert: drowsyPictures >= 21,
        face_detected: true,
      }
      const statusPacket = '42' + JSON.stringify(packet)
      socket.send(statusPacket)
    })
  })
  await startCameraPreview(page)
  await page.getByRole('button', { name: 'Publish', exact: true }).click()
  const results = page.getByRole('region', { name: 'Detection results' })
  await expect(
    page.getByRole('heading', { name: 'Drowsiness detected' }),
  ).toBeVisible()
  await expect(results.getByText('22 of 42 valid pictures')).toBeVisible()
  drowsyPictures = 20
  await expect(
    page.getByRole('heading', { name: 'Monitoring', exact: true }),
  ).toBeVisible()
  await expect(results.getByText('20 of 42 valid pictures')).toBeVisible()
  await page.getByRole('button', { name: 'Stop', exact: true }).click()
  await page.getByRole('button', { name: 'Start camera' }).click()
  await expect(results.getByText('20 of 42 valid pictures')).toHaveCount(0)
})

test('waits for enough valid pictures and does not invent observations between messages', async ({
  page,
}) => {
  let sentStatus = false
  await page.routeWebSocket('**/api/socket.io/**', (socket) => {
    const server = socket.connectToServer()
    server.onMessage((message) => {
      if (typeof message !== 'string' || !message.startsWith('42["status",')) {
        socket.send(message)
        return
      }
      if (sentStatus) return
      sentStatus = true
      const packet = JSON.parse(message.slice(2)) as [
        string,
        Record<string, unknown>,
      ]
      packet[1].detection = {
        captured_at_ms: 0,
        ear: 0.1,
        fatigue_probability: 0.9,
        minute: {
          valid_samples: 10,
          drowsy_samples: 10,
          unavailable_samples: 50,
          window_seconds: 60,
        },
        alert: false,
        face_detected: true,
      }
      const statusPacket = '42' + JSON.stringify(packet)
      socket.send(statusPacket)
    })
  })
  await startCameraPreview(page)
  await page.getByRole('button', { name: 'Publish', exact: true }).click()
  await expect(
    page.getByRole('heading', { name: 'Gathering observations' }),
  ).toBeVisible()
  const results = page.getByRole('region', { name: 'Detection results' })
  await expect(results.getByText('10 of 10 valid pictures')).toBeVisible()
  await page.waitForTimeout(1500)
  await expect(results.getByText('10 of 10 valid pictures')).toBeVisible()
  await expect(
    page.getByRole('heading', { name: 'Drowsiness detected' }),
  ).toHaveCount(0)
  await page.getByRole('button', { name: 'Stop', exact: true }).click()
})

test('keeps emitting frames without receiving detection or diagnostic messages', async ({
  page,
}) => {
  let uploadedFrames = 0
  await page.routeWebSocket('**/api/socket.io/**', (socket) => {
    const server = socket.connectToServer()
    socket.onMessage((message) => {
      if (typeof message !== 'string') uploadedFrames += 1
      server.send(message)
    })
    server.onMessage((message) => {
      if (typeof message === 'string' && message.startsWith('42["status",'))
        return
      socket.send(message)
    })
  })
  await startCameraPreview(page)
  await page.getByRole('button', { name: 'Publish', exact: true }).click()
  await expect(page.getByRole('status')).toHaveText('Live')
  await expect.poll(() => uploadedFrames).toBeGreaterThanOrEqual(3)
  await expect(
    page.getByRole('heading', { name: 'Waiting for detection' }),
  ).toBeVisible()
  await page.getByRole('button', { name: 'Stop', exact: true }).click()
})
