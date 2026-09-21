// Dependency-free tests for refresh behavior; these do not test browser layout.
const { readFileSync } = require("node:fs");
const { runInNewContext } = require("node:vm");
const { test } = require("node:test");
const assert = require("node:assert/strict");
const source = readFileSync(require("node:path").join(__dirname, "../static/js/table-live.js"), "utf8");

function page() {
    const timers = new Map(), events = {}, requests = [];
    let sequence = 0, replacements = 0;
    const message = {}, filterInput = {}, tableLink = {}, replacement = {};
    const document = { hidden: false, activeElement: null, addEventListener: (name, fn) => { events[name] = fn; } };
    const current = {
        contains: (element) => element === tableLink,
        replaceWith: (element) => { assert.equal(element, replacement); replacements++; },
    };
    const elements = {
        "[data-live-message]": message,
        "[data-table-filters]": { contains: (element) => element === filterInput },
        "[data-live-refresh]": { addEventListener: (name, fn) => { events[name] = fn; } },
        "#table-live-results": current,
    };
    document.querySelector = () => ({ querySelector: (selector) => elements[selector] });
    let respond = async () => ({ ok: true, status: 200, text: async () => "results" });
    runInNewContext(source, {
        document,
        window: { location: { href: "http://localhost/ban/?current_status=occupied&page=2" }, addEventListener: document.addEventListener },
        AbortController,
        setTimeout: (fn, delay) => { timers.set(++sequence, { fn, delay }); return sequence; },
        clearTimeout: (id) => timers.delete(id),
        fetch: (url, options) => { requests.push({ url, options }); return respond(options); },
        DOMParser: class { parseFromString(html) { return { querySelector: () => html === "results" ? replacement : null }; } },
    });
    return {
        document, events, message, requests, filterInput, tableLink,
        get replacements() { return replacements; },
        set respond(fn) { respond = fn; },
        hasTimer(delay) { return [...timers.values()].some((timer) => timer.delay === delay); },
        async tick(delay = 15000) {
            const entry = [...timers].find(([, timer]) => timer.delay === delay);
            assert.ok(entry, `Missing timer ${delay}`);
            timers.delete(entry[0]);
            await entry[1].fn();
        },
    };
}

test("refresh preserves the current URL filters and only replaces results", async () => {
    const p = page();
    await p.tick();
    assert.equal(p.requests[0].url, "http://localhost/ban/?current_status=occupied&page=2");
    assert.equal(p.requests[0].options.headers["X-Table-Refresh"], "1");
    assert.equal(p.requests[0].options.cache, "no-store");
    assert.equal(p.replacements, 1);
    assert.ok(p.hasTimer(15000));
});

test("typing and focused table links defer refresh", async () => {
    const p = page();
    for (const element of [p.filterInput, p.tableLink]) {
        p.document.activeElement = element;
        await p.tick();
        assert.equal(p.requests.length, 0);
        assert.ok(p.hasTimer(15000));
    }
});

test("hidden tabs pause and returning to the tab refreshes", async () => {
    const p = page();
    p.document.hidden = true;
    p.events.visibilitychange();
    assert.equal(p.hasTimer(15000), false);
    assert.equal(p.requests.length, 0);
    p.document.hidden = false;
    p.events.visibilitychange();
    await new Promise(setImmediate);
    assert.equal(p.replacements, 1);
});

test("expired login or revoked access stops refresh and preserves navigation fallback", async () => {
    for (const response of [{ ok: true, redirected: true }, { status: 401 }, { status: 403 }]) {
        const p = page();
        p.respond = async () => response;
        await p.tick();
        assert.equal(p.replacements, 0);
        assert.equal(p.hasTimer(15000), false);
        assert.match(p.message.textContent, /tải lại trang/);
        p.events.click({ preventDefault: () => assert.fail("Reload link must remain usable") });
    }
});

test("network failure and invalid responses retain old results and retry", async () => {
    for (const respond of [
        async () => { throw new Error("Offline"); },
        async () => ({ ok: false, status: 500 }),
        async () => ({ ok: true, text: async () => "login page" }),
    ]) {
        const p = page();
        p.respond = respond;
        await p.tick();
        assert.equal(p.replacements, 0);
        assert.match(p.message.textContent, /dữ liệu lần trước/);
        assert.ok(p.hasTimer(15000));
    }
});

test("slow requests time out and never overlap", async () => {
    const p = page();
    p.respond = ({ signal }) => new Promise((resolve, reject) => {
        signal.addEventListener("abort", () => reject(new Error("Aborted")));
    });
    const pending = p.tick();
    p.events.click({ preventDefault() {} });
    assert.equal(p.requests.length, 1);
    await p.tick(10000);
    await pending;
    assert.ok(p.requests[0].options.signal.aborted);
    assert.ok(p.hasTimer(15000));
});
