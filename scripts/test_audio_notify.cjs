// Dependency-free checks for the notification audio entry point.
const { readFileSync } = require("node:fs");
const { join } = require("node:path");
const { runInNewContext } = require("node:vm");
const { test } = require("node:test");
const assert = require("node:assert/strict");

const source = readFileSync(join(__dirname, "../static/js/audio-notify.js"), "utf8");

test("notification audio uses the matching preloaded project WAV asset", async () => {
  const created = [];
  const listeners = {};
  class FakeAudio {
    constructor(url) {
      this.url = url;
      this.preload = "";
      this.volume = 1;
      this.muted = false;
      this.events = {};
      this.playCalls = 0;
      created.push(this);
    }
    addEventListener(name, handler) { this.events[name] = handler; }
    load() {}
    play() {
      this.playCalls += 1;
      return Promise.resolve();
    }
    pause() {}
  }

  const localStorage = new Map();
  const window = { setTimeout, QLNHAudio: null };
  const document = {
    addEventListener: (name, handler) => { listeners[name] = handler; },
    querySelectorAll: () => [],
  };
  runInNewContext(source, {
    Audio: FakeAudio,
    Promise,
    document,
    localStorage: {
      getItem: (key) => localStorage.get(key) || null,
      setItem: (key, value) => localStorage.set(key, value),
    },
    requestAnimationFrame: (callback) => callback(),
    window,
  });

  window.QLNHAudio.play("payment");
  await new Promise(setImmediate);

  const audio = created.at(-1);
  assert.equal(audio.url, "/static/audio/payment.wav");
  assert.equal(audio.preload, "auto");
  assert.equal(audio.volume, 0.9);
  assert.equal(audio.playCalls, 1);
  assert.ok(listeners.DOMContentLoaded);
});
