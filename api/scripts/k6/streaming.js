import { check, sleep } from "k6";
import exec from "k6/execution";
import { Counter, Trend } from "k6/metrics";
import { WebSocket } from "k6/websockets";
import {
  clearInterval,
  clearTimeout,
  setInterval,
  setTimeout,
} from "k6/timers";

const cameras = Number(__ENV.CAMERAS);
const seconds = Number(__ENV.SECONDS);
const fps = Number(__ENV.FPS);
const rampSeconds = Number(__ENV.RAMP_SECONDS);
const warmupSeconds = Number(__ENV.WARMUP_SECONDS);
const paths = JSON.parse(
  __ENV.FRAME_PATHS ?? '["../../.local/k6/portrait.jpg"]',
);
const loadFrameImage = (path) => {
  const bytes = open(path, "b");
  return new Uint8Array(bytes);
};
const images = paths.map(loadFrameImage);
const baseUrl = __ENV.BASE_URL ?? "http://127.0.0.1:8001";

if (
  !Number.isInteger(cameras) ||
  cameras < 1 ||
  !Number.isFinite(seconds) ||
  seconds < 1 ||
  !Number.isFinite(fps) ||
  fps <= 0 ||
  fps > 10 ||
  !Number.isFinite(rampSeconds) ||
  rampSeconds < 0 ||
  !Number.isFinite(warmupSeconds) ||
  warmupSeconds < 0 ||
  !images.length
) {
  throw new Error(
    "Use positive CAMERAS/SECONDS, FPS in (0, 10], and nonnegative ramp/warm-up durations",
  );
}

const connected = new Counter("publishers_connected");
const errors = new Counter("stream_errors");
const shutdownErrors = new Counter("shutdown_errors");
const sent = new Counter("frames_sent");
const skipped = new Counter("frames_skipped");
const received = new Counter("frames_received");
const processed = new Counter("frames_processed");
const replaced = new Counter("frames_replaced");
const stale = new Counter("frames_stale");
const receivedFps = new Trend("camera_received_fps");
const processedFps = new Trend("camera_processed_fps");
const rollingFps = new Trend("camera_30s_processed_fps");
const sessionFps = new Trend("camera_session_processed_fps");
const resultAge = new Trend("result_age_ms", true);
const pending = new Trend("pending_frames");

export const options = {
  scenarios: {
    cameras: {
      executor: "per-vu-iterations",
      vus: cameras,
      iterations: 1,
      maxDuration: `${Math.ceil(rampSeconds + warmupSeconds + seconds + 15)}s`,
    },
  },
  summaryTrendStats: ["avg", "min", "med", "max", "p(95)"],
  thresholds: {
    checks: ["rate==1"],
    publishers_connected: [`count==${cameras}`],
    stream_errors: ["count==0"],
    shutdown_errors: ["count==0"],
    pending_frames: ["max<=1"],
    ...(__ENV.MIN_PROCESSED_FPS
      ? {
          camera_30s_processed_fps: [`min>=${Number(__ENV.MIN_PROCESSED_FPS)}`],
        }
      : {}),
  },
};

export default () => {
  const seat = exec.vu.idInTest;
  const start = exec.scenario.startTime;
  const steadyStart = start + (rampSeconds + warmupSeconds) * 1000;
  const end = steadyStart + seconds * 1000;
  const connectAt =
    start + (cameras > 1 ? (seat - 1) / (cameras - 1) : 0) * rampSeconds * 1000;
  const connectionDelaySeconds = Math.max(0, connectAt - Date.now()) / 1000;
  sleep(connectionDelaySeconds);
  const captureStart = Date.now();
  const socketBaseUrl = baseUrl.replace(/^http/, "ws").replace(/\/$/, "");
  const socketUrl = `${socketBaseUrl}/api/socket.io/?EIO=4&transport=websocket`;
  const socket = new WebSocket(socketUrl, [], {
    headers: { Origin: __ENV.ORIGIN ?? "http://localhost:3000" },
  });
  const tags = { seat: String(seat) };
  let authenticatedAt = 0;
  let lastStatusAt = captureStart;
  let stopping = false;
  let failed = false;
  let intentional = false;
  let frameId = 0;
  let captureMs = -1;
  let sender;
  let watchdog;
  let finish;
  let previous;
  let first;
  let latest;
  let sawCnn = false;
  let sawEar = false;
  let windows = 0;
  const window = [];
  errors.add(0, tags);
  shutdownErrors.add(0, tags);

  const stop = () => {
    if (stopping) return;
    stopping = true;
    if (sender !== undefined) clearInterval(sender);
    if (watchdog !== undefined) clearInterval(watchdog);
    if (finish !== undefined) clearTimeout(finish);
    if (socket.readyState === WebSocket.OPEN) socket.close(1000);
  };
  const fail = (category, code = "unknown") => {
    if (failed) return;
    failed = true;
    (intentional ? shutdownErrors : errors).add(1, { ...tags, category, code });
    stop();
  };
  const sendFrame = () => {
    if (stopping) return;
    if (Date.now() >= end) {
      intentional = true;
      stop();
      return;
    }
    if (socket.bufferedAmount > 0) {
      if (Date.now() >= steadyStart) skipped.add(1, tags);
      return;
    }
    const image = images[Math.floor(Math.random() * images.length)];
    const payload = new ArrayBuffer(12 + image.length);
    const header = new DataView(payload);
    captureMs = Math.max(Date.now() - captureStart, captureMs + 1);
    header.setUint32(0, ++frameId, false);
    header.setFloat64(4, captureMs, false);
    const jpegBytes = new Uint8Array(payload, 12);
    jpegBytes.set(image);
    socket.send('451-["frame",{"_placeholder":true,"num":0}]');
    socket.send(payload);
    if (Date.now() >= steadyStart) sent.add(1, tags);
  };

  const recordStreamStatus = (status) => {
    const now = Date.now();
    lastStatusAt = now;
    if (now < steadyStart || now >= end) return;
    const diagnostics = status.diagnostics;
    latest = { at: now, count: diagnostics.processed_frames };
    first ??= latest;
    window.push(latest);
    while (window.length > 1 && window[1].at <= now - 30000) window.shift();
    if (now - window[0].at >= 30000) {
      rollingFps.add(
        ((latest.count - window[0].count) * 1000) / (now - window[0].at),
        tags,
      );
      windows += 1;
    }
    // First steady status establishes the baseline after warm-up.
    if (previous) {
      received.add(
        diagnostics.received_frames - previous.received_frames,
        tags,
      );
      processed.add(
        diagnostics.processed_frames - previous.processed_frames,
        tags,
      );
      replaced.add(
        diagnostics.replaced_frames - previous.replaced_frames,
        tags,
      );
      stale.add(diagnostics.stale_frames - previous.stale_frames, tags);
      receivedFps.add(diagnostics.received_fps, tags);
      processedFps.add(diagnostics.processed_fps, tags);
    }
    previous = diagnostics;
    pending.add(diagnostics.pending_frames, tags);
    if (status.detection) {
      sawCnn ||= status.detection.fatigue_probability !== null;
      sawEar ||= status.detection.ear !== null;
      resultAge.add(now - captureStart - status.detection.captured_at_ms, tags);
    }
  };

  socket.onopen = () => {
    if (stopping) socket.close(1000);
  };
  socket.onmessage = ({ data }) => {
    if (stopping) return;
    if (data.startsWith("0")) {
      const authentication = {
        seat_id: seat,
        token: `demo-room-101-seat-${seat}`,
        diagnostics: true,
      };
      const authenticationJson = JSON.stringify(authentication);
      socket.send(`40${authenticationJson}`);
    } else if (data === "2") {
      socket.send("3"); // Engine.IO heartbeat.
    } else if (data.startsWith("40")) {
      authenticatedAt = Date.now();
      connected.add(1, tags);
      sendFrame();
      sender = setInterval(sendFrame, 1000 / fps);
    } else if (data.startsWith("44")) {
      const errorPayload = data.slice(2);
      const error = JSON.parse(errorPayload);
      const code = error.data?.code ?? "unknown";
      fail("authentication", code);
    } else if (data === "41" || data === "1") {
      fail("disconnect");
    } else if (data.startsWith("42")) {
      const eventPayload = data.slice(2);
      const [event, status] = JSON.parse(eventPayload);
      if (event === "stream_error") return fail("server", status.code);
      if (event !== "status") return;
      recordStreamStatus(status);
    }
  };
  watchdog = setInterval(() => {
    if (Date.now() - lastStatusAt > 10000) {
      fail("timeout", authenticatedAt ? "status" : "authentication");
    }
  }, 1000);
  finish = setTimeout(
    () => {
      intentional = true;
      stop();
    },
    Math.max(0, end - Date.now()),
  );
  socket.onerror = () => fail("transport");
  socket.onclose = ({ code }) => {
    if (failed || !intentional || code !== 1000) {
      const closeDetails = JSON.stringify({ seat, close_code: code });
      console.warn(closeDetails);
    }
    if (!intentional && !failed) fail("disconnect", String(code));
    else if (intentional && code !== 1000) fail("disconnect", String(code));
    stop();
    const elapsed = first && latest ? latest.at - first.at : 0;
    const sessionProcessedFps =
      elapsed > 0 ? ((latest.count - first.count) * 1000) / elapsed : 0;
    sessionFps.add(sessionProcessedFps, tags);
    check(
      null,
      {
        "publisher completed full load window": () =>
          intentional && !failed && authenticatedAt <= steadyStart,
        "publisher received steady diagnostics": () =>
          !!first && elapsed >= (seconds - 3) * 1000,
        "publisher produced CNN and EAR results": () => sawCnn && sawEar,
        "publisher has required 30-second samples": () =>
          !__ENV.MIN_PROCESSED_FPS || windows > 0,
      },
      tags,
    );
  };
};
