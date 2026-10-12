// Dependency-free checks for POS/Kitchen polling policy.
const { readFileSync } = require("node:fs");
const { join } = require("node:path");
const { runInNewContext } = require("node:vm");
const { test } = require("node:test");
const assert = require("node:assert/strict");

const source = readFileSync(join(__dirname, "../static/js/staff-polling.js"), "utf8");

class TestCustomEvent {
  constructor(type, options = {}) {
    this.type = type;
    this.detail = options.detail;
  }
}

function page(initialResponses = []) {
  const timers = new Map();
  const handlers = {};
  const requests = [];
  const dispatched = [];
  const badge = { innerHTML: "", classList: { remove() {} } };
  const root = {
    dataset: { stateUrl: "/sales/state/" },
    querySelector: (selector) => (selector === ".sales-live" ? badge : null),
  };
  const document = {
    hidden: false,
    querySelector: (selector) => (selector === "[data-live-workspace]" ? root : null),
    addEventListener: (name, handler) => { handlers[name] = handler; },
    dispatchEvent: (event) => { dispatched.push(event); },
  };
  let timerSequence = 0;
  const responses = [...initialResponses];
  const defaultResponse = {
    ok: true,
    status: 304,
    headers: { get: () => '"v1"' },
    text: async () => "",
  };
  const context = {
    AbortController,
    CustomEvent: TestCustomEvent,
    JSON,
    Promise,
    document,
    window: {
      setTimeout: (fn, delay) => {
        timerSequence += 1;
        timers.set(timerSequence, { fn, delay });
        return timerSequence;
      },
      clearTimeout: (timerId) => timers.delete(timerId),
    },
    fetch: async (url, options) => {
      requests.push({ url, options });
      return responses.shift() || defaultResponse;
    },
  };
  runInNewContext(source, context);

  return {
    badge,
    document,
    dispatched,
    handlers,
    requests,
    respond(response) { responses.push(response); },
    hasTimer(delay) { return [...timers.values()].some((timer) => timer.delay === delay); },
    async settle() { await new Promise(setImmediate); },
    async tick(delay) {
      const entry = [...timers].find(([, timer]) => timer.delay === delay);
      assert.ok(entry, `Missing timer ${delay}`);
      timers.delete(entry[0]);
      await entry[1].fn();
      await this.settle();
    },
  };
}

test("uses ETag polling every five seconds without EventSource", async () => {
  assert.doesNotMatch(source, /EventSource|data-stream-url|streamUrl/);
  const p = page([{
    ok: true,
    status: 200,
    headers: { get: () => '"v1"' },
    text: async () => JSON.stringify({ tables: { count: 1 } }),
  }]);
  await p.settle();

  assert.equal(p.requests.length, 1);
  assert.equal(p.requests[0].url, "/sales/state/");
  assert.equal(p.requests[0].options.headers["X-Requested-With"], "XMLHttpRequest");
  assert.match(p.badge.innerHTML, /5 giây/);
  assert.ok(p.hasTimer(5000));

  await p.tick(5000);
  assert.equal(p.requests[1].options.headers["If-None-Match"], '"v1"');
  assert.ok(p.hasTimer(5000));
});

test("refreshes promptly after a state change and slows to thirty seconds in background", async () => {
  const p = page([{
    ok: true,
    status: 200,
    headers: { get: () => '"v1"' },
    text: async () => JSON.stringify({ tables: { count: 1 } }),
  }]);
  await p.settle();

  p.respond({
    ok: true,
    status: 200,
    headers: { get: () => '"v2"' },
    text: async () => JSON.stringify({ tables: { count: 2 } }),
  });
  await p.tick(5000);
  assert.equal(p.dispatched.at(-1).type, "workspace:state-change");
  assert.equal(p.dispatched.at(-1).detail.tables.count, 2);

  p.document.hidden = true;
  p.handlers.visibilitychange();
  assert.match(p.badge.innerHTML, /30 giây/);
  assert.ok(p.hasTimer(30000));
});

test("backs off after a network failure", async () => {
  const p = page([{
    ok: false,
    status: 503,
    headers: { get: () => null },
    text: async () => "",
  }]);
  await p.settle();
  assert.ok(p.hasTimer(10000));
});
