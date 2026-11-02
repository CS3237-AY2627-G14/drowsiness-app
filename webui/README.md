# Drowsiness web client

React camera client built with Vite, TanStack Router, and TanStack Query. It
publishes camera frames to the [API](../api/README.md) over Socket.IO.

## Setup and development

Requires Node.js 22.x (22.12+) and npm. From the repository root:

```bash
cd webui
cp .env.example .env
npm ci
npm run dev
```

Skip the copy if you already have `.env`. Start the API separately using the
[API guide](../api/README.md), then open http://localhost:3000/streaming. Vite proxies
`/api` requests to `http://127.0.0.1:8000`. Select a seat, start the camera, then
Publish. Demo tokens look like `demo-room-101-seat-1`.

Camera settings are listed in [.env.example](.env.example). Overrides can go in
`.env.local`; restart Vite after changing them. Camera access requires localhost
or trusted HTTPS. For remote cameras, set both `DEV_TLS_CERT` and `DEV_TLS_KEY`
in `.env.local` and add the exact HTTPS origin to the API's
`DROWSINESS_ALLOWED_ORIGINS`. Certificate paths resolve from `webui/`.

## Choosing a camera

Use **Camera** to choose a connected webcam or a virtual/remote camera exposed
as a webcam by your operating system. Click **Refresh cameras** after connecting
one. Browsers may hide cameras and names until permission is granted: start the
default camera, allow access, then click **Stop** and choose your camera.
Stop before switching cameras. A disconnected selection is shown as unavailable;
choose another camera or reconnect it before starting again.

For a camera on another phone or computer, open this page on that device using
trusted HTTPS and publish from there. The camera selector lists devices available
to the current browser; it does not accept IP camera or RTSP stream URLs.
On Windows, enable camera access for desktop apps in Windows camera privacy
settings as well as camera permission for this site in your browser.

`VITE_VIDEO_FPS` controls JPEG upload sampling. The camera uses its supported
capture rate independently so low upload rates do not prevent camera startup.

## Checks

From `webui/`:

```bash
npm run typecheck
npm run lint
npm run check
npm run test
npm run build
```

For browser tests, run the API and Vite with ten demo seats and Chrome installed:

```bash
npx playwright install chrome
npm run test:e2e
```

On WSL, use `npx playwright install --with-deps chrome`. Tests use a synthetic
camera. Run `npx -y react-doctor@latest . --verbose --scope full` after React changes.
