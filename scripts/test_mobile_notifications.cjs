const {readFileSync} = require("node:fs");
const {join} = require("node:path");
const {runInNewContext} = require("node:vm");
const {test} = require("node:test");
const assert = require("node:assert/strict");
const pollSource = readFileSync(join(__dirname, "../static/js/nav-notifications.js"), "utf8");
const mobileSource = readFileSync(join(__dirname, "../static/js/mobile-notifications.js"), "utf8");
const flush = () => new Promise(setImmediate);
function harness() {
  const handlers = {}, timers = new Map(), requests = [], sounds = [], events = [];
  const root = {dataset: {notificationUrl: "/notifications/state/?mobile=1", mobileUrl: "/sales/mobile/"}};
  const status = {textContent: "", classList: {toggle() {}}};
  const panel = {open: false, querySelector: () => status, showModal() {this.open = true;}, close() {this.open = false;}, contains: () => false};
  const toast = {hidden: true}, message = {textContent: ""};
  const nodes = {"[data-notification-url]": root, "[data-mobile-notification-panel]": panel, "[data-mobile-notification-toast]": toast, "[data-mobile-notification-message]": message};
  const document = {
    hidden: false, querySelector: s => nodes[s] || null, querySelectorAll: () => [],
    addEventListener(name, fn) {(handlers[name] ||= []).push(fn);},
    dispatchEvent(e) {events.push(e); (handlers[e.type] || []).forEach(fn => fn(e));}
  };
  let id = 0, queued = [], fail = false;
  const setTimeout = (fn, delay) => {timers.set(++id, {fn, delay}); return id;};
  const clearTimeout = id => timers.delete(id);
  const window = {addEventListener(name, fn) {(handlers[name] ||= []).push(fn);}, QLNHAudio: {play: type => sounds.push(type)}};
  const payload = count => ({counts: {total: count, tasks: count}, entries: [{key: "service", count, label: "Yêu cầu phục vụ", url: "/sales/mobile/?page=tasks#m-requests"}]});
  const response = (body, code=200) => ({status: code, ok: code===200, redirected: false, headers: {get: () => '"notifications-v1"'}, json: async() => body});
  queued.push(response(payload(1)));
  const context = {
    document, window, location: {origin: "http://127.0.0.1"}, URL, AbortController, console, setTimeout, clearTimeout,
    CustomEvent: class {constructor(type, opts) {this.type = type; this.detail = opts?.detail;}},
    fetch: async (url, options) => {requests.push({url, options}); if (fail) throw Error("offline"); return queued.shift() || response(null, 304);}
  };
  runInNewContext(mobileSource, context);
  runInNewContext(pollSource, context);
  const event = (type, detail) => document.dispatchEvent({type, detail});
  const tick = async delay => {
    const entry = [...timers].find(([,timer]) => timer.delay===delay);
    assert.ok(entry, "Expected timer at " + delay);
    timers.delete(entry[0]); entry[1].fn(); await flush();
  };
  return {document, panel, toast, message, status, requests, sounds, events, timers, payload, response, event, tick, queue: body => queued.push(body), offline: value => {fail=value;}};
}
test("mobile alerts only for increased permitted work; DOM navigation and decreases do not repeat sounds", async () => {
  const h=harness(); await flush();
  assert.equal(h.sounds.length, 0);
  assert.equal(h.toast.hidden, true);
  assert.equal(h.requests[0].options.credentials, "same-origin");
  h.queue(h.response(h.payload(2))); await h.tick(5000);
  assert.equal(h.toast.hidden, false);
  assert.deepEqual(h.sounds, ["service"]);
  assert.ok(h.message.textContent.includes("2"));
  h.event("mobile:page-ready"); await flush(); await h.tick(5000);
  assert.equal(h.sounds.length, 1);
  h.queue(h.response(h.payload(0))); await h.tick(5000);
  assert.equal(h.sounds.length, 1);
  assert.equal(h.requests[1].options.headers["If-None-Match"], '"notifications-v1"');
});
test("network errors keep the last snapshot and back off; hidden tabs do not poll", async () => {
  const h=harness(); await flush();
  const updates = () => h.events.filter(e=>e.type==="notifications:updated").length;
  const before=updates(); h.offline(true); await h.tick(5000);
  assert.equal(updates(), before);
  assert.ok(h.status.textContent.includes("Chưa kết nối"));
  assert.ok([...h.timers.values()].some(t=>t.delay===10000));
  h.document.hidden=true; h.event("visibilitychange");
  assert.ok(![...h.timers.values()].some(t=>t.delay===10000));
  h.offline(false); h.document.hidden=false; h.event("visibilitychange"); await flush();
  assert.equal(h.requests.length, 3);
  assert.ok(!h.requests[2].options.headers["If-None-Match"]);
});
test("lost access clears private notification entries and stops polling", async () => {
  const h=harness(); await flush();
  h.queue(h.response(null,403)); await h.tick(5000);
  const last=h.events.filter(e=>e.type==="notifications:updated").at(-1);
  assert.equal(last.detail.counts.total,0);
  assert.equal(last.detail.entries.length,0);
  assert.ok(h.status.textContent.includes("quyền đã đổi"));
  assert.ok(![...h.timers.values()].some(t=>t.delay===5000));
});
test("invalid responses do not replace a valid snapshot", async () => {
  const h=harness(); await flush();
  const before=h.events.filter(e=>e.type==="notifications:updated").length;
  h.queue(h.response({counts: {total:1}, entries: [{key:"bad",label:"bad", count:-1}]}));
  await h.tick(5000);
  assert.equal(h.events.filter(e=>e.type==="notifications:updated").length,before);
  assert.equal(h.sounds.length,0);
});
test("notification dialog opens from delegated controls after page replacement", async () => {
  const h=harness(); await flush();
  const target={closest: selector=>selector==="[data-mobile-notification-open]" ? {} : null};
  h.document.dispatchEvent({type:"click", target});
  assert.equal(h.panel.open,true);
  h.queue(h.response(h.payload(2))); await h.tick(5000);
  assert.equal(h.toast.hidden,true);
  assert.equal(h.sounds.length,1);
});

test("SPA navigation requests fresh state without replaying a cached snapshot over server counts", async () => {
  const h=harness(); await flush();
  const updates=()=>h.events.filter(e=>e.type==="notifications:updated");
  assert.equal(updates().length,1);
  h.queue(h.response(h.payload(3)));
  h.event("mobile:page-ready");
  assert.equal(updates().length,1);
  await flush();
  assert.equal(updates().at(-1).detail.counts.total,3);
  assert.equal(h.requests.length,2);
  assert.ok(!h.requests[1].options.headers["If-None-Match"]);
});

test("payment and QR order alerts use matching sound types without replaying newly granted categories", async () => {
  const h=harness(); await flush();
  const state=(payments, orders)=>({counts:{total:payments+orders},entries:[
    {key:"payments",count:payments,label:"Payment",url:"/sales/mobile/?page=tasks#m-payments"},
    {key:"qr_orders",count:orders,label:"QR order",url:"/sales/mobile/?page=tasks#m-requests"}
  ]});
  h.event("notifications:updated",state(0,0));
  assert.equal(h.sounds.length,0);
  h.event("notifications:updated",state(1,0));
  h.event("notifications:updated",state(1,1));
  assert.deepEqual(h.sounds,["payment","order"]);
});
