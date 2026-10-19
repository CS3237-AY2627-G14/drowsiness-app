import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

// Exercise the actual script with a fake clock and transport, without a server.
const createTestHarness = () => {
  let now = 100000;
  let socket;
  const timers = new Map();
  const metrics = new Map();
  const checks = [];
  let nextTimer = 0;
  const Metric = class {
    constructor(name) {
      this.name = name;
    }
    add(value, tags) {
      if (!metrics.has(this.name)) metrics.set(this.name, []);
      metrics.get(this.name).push({ value, tags });
    }
  };
  const FakeSocket = class {
    static OPEN = 1;
    constructor() {
      socket = this;
      this.readyState = 1;
      this.bufferedAmount = 0;
      this.sent = [];
      this.closes = 0;
    }
    send(data) {
      this.sent.push(data);
    }
    close() {
      this.closes += 1;
      this.readyState = 2;
    }
  };
  const context = {
    __ENV: {
      CAMERAS: "1",
      FPS: "1",
      SECONDS: "40",
      RAMP_SECONDS: "0",
      WARMUP_SECONDS: "10",
    },
    open: () => new ArrayBuffer(3),
    sleep: () => {},
    exec: { vu: { idInTest: 1 }, scenario: { startTime: 100000 } },
    Date: { now: () => now },
    Counter: Metric,
    Trend: Metric,
    WebSocket: FakeSocket,
    setInterval: (callback) => {
      timers.set(++nextTimer, callback);
      return nextTimer;
    },
    setTimeout: (callback) => {
      timers.set(++nextTimer, callback);
      return nextTimer;
    },
    clearInterval: (id) => timers.delete(id),
    clearTimeout: (id) => timers.delete(id),
    check: (_, predicates) =>
      checks.push(...Object.values(predicates).map((predicate) => predicate())),
  };
  const scriptPath = new URL("./streaming.js", import.meta.url);
  const scriptSource = readFileSync(scriptPath, "utf8");
  const scriptWithoutImports = scriptSource.replace(
    /^import[\s\S]*?from ["'][^"']+["'];?\r?\n/gm,
    "",
  );
  const scriptWithoutOptionsExport = scriptWithoutImports.replace(
    "export const options",
    "const options",
  );
  const source = scriptWithoutOptionsExport.replace(
    "export default () =>",
    "globalThis.run = () =>",
  );
  vm.runInNewContext(`${source}\nrun();`, context);
  const message = (data, at = now) => {
    now = at;
    socket.onmessage({ data });
  };
  message("0{}");
  message("40{}", 100010);
  const status = (at, count) => {
    const packet = [
      "status",
      {
        diagnostics: {
          received_frames: count,
          processed_frames: count,
          replaced_frames: 0,
          stale_frames: 0,
          received_fps: 5,
          processed_fps: 5,
          pending_frames: 1,
        },
        detection: {
          captured_at_ms: at - 100000 - 100,
          ear: 0.3,
          fatigue_probability: 0.1,
        },
      },
    ];
    const packetJson = JSON.stringify(packet);
    message(`42${packetJson}`, at);
  };
  return {
    socket,
    timers,
    metrics,
    checks,
    message,
    status,
    setTime: (at) => {
      now = at;
    },
  };
};

test("normal shutdown clears timers, closes once and records no stream errors", () => {
  const harness = createTestHarness();
  for (let at = 110000; at <= 149000; at += 1000)
    harness.status(at, (at - 100000) / 200);
  const finish = harness.timers.get(2);
  harness.setTime(150000);
  finish();
  harness.socket.readyState = 3;
  harness.socket.onclose({ code: 1000 });
  assert.equal(harness.socket.closes, 1);
  assert.equal(harness.timers.size, 0);
  assert.ok(harness.checks.every(Boolean));
  assert.equal(
    harness.metrics
      .get("stream_errors")
      .reduce((sum, point) => sum + point.value, 0),
    0,
  );
  assert.ok(
    harness.metrics
      .get("camera_30s_processed_fps")
      .every((point) => point.value === 5),
  );
});

test("counter deltas exclude warm-up and use elapsed time with delayed statuses", () => {
  const harness = createTestHarness();
  harness.status(109000, 500);
  harness.status(110000, 600);
  harness.status(125000, 630);
  harness.status(141000, 662);
  assert.equal(
    harness.metrics
      .get("frames_processed")
      .reduce((sum, point) => sum + point.value, 0),
    62,
  );
  assert.equal(harness.metrics.get("camera_30s_processed_fps")[0].value, 2);
});

test("backed-up transport skips frames and shutdown failures have their own counter", () => {
  const harness = createTestHarness();
  harness.setTime(120000);
  harness.socket.bufferedAmount = 10;
  const sends = harness.socket.sent.length;
  harness.timers.get(3)();
  assert.equal(harness.socket.sent.length, sends);
  assert.equal(harness.metrics.get("frames_skipped")[0].value, 1);
  harness.timers.get(2)();
  harness.socket.onerror();
  assert.equal(harness.metrics.get("shutdown_errors").at(-1).value, 1);
  assert.equal(harness.metrics.get("stream_errors").at(-1).value, 0);
});

test("server errors stop sending and retain the sanitized error code", () => {
  const harness = createTestHarness();
  harness.message('42["stream_error",{"code":"invalid_frame"}]');
  assert.equal(
    harness.metrics.get("stream_errors").at(-1).tags.code,
    "invalid_frame",
  );
  assert.equal(harness.timers.size, 0);
  harness.socket.readyState = 3;
  harness.socket.onclose({ code: 1000 });
  assert.ok(harness.checks.some((passed) => !passed));
});
