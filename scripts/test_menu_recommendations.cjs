const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {runInNewContext} = require('node:vm');
const {test} = require('node:test');
const assert = require('node:assert/strict');
const source = readFileSync(join(__dirname, '../static/js/menu-recommendations.js'), 'utf8');

class Element {
  constructor(tag = 'div') { this.tag = tag; this.children = []; this.dataset = {}; this.hidden = true; this.isConnected = true; this.listeners = {}; }
  append(...nodes) { this.children.push(...nodes); }
  appendChild(node) { this.children.push(node); }
  replaceChildren() { this.children = []; }
  setAttribute() {}
  addEventListener(name, callback) { this.listeners[name] = callback; }
  querySelectorAll(selector) { return this.children.flatMap(child => [...(child.tag === selector ? [child] : []), ...child.querySelectorAll(selector)]); }
}

function setup() {
  const list = new Element(), widget = new Element();
  widget.dataset = {recommendationMode: 'qr', recommendationUrl: '/menu/recommendations/'};
  widget.append(list); widget.querySelector = () => list;
  const cards = ['1', '2', '3', '4'].map(id => ({dataset: {id}, querySelector: () => ({disabled: false, click() { clicks.push(id); }})}));
  const handlers = {}, timers = new Map(), requests = [], clicks = [];
  let sequence = 0;
  const document = {
    addEventListener(name, callback) { (handlers[name] ||= []).push(callback); },
    querySelectorAll(selector) { return selector === '[data-qr-dish]' ? cards : [widget]; },
    createElement(tag) { return new Element(tag); },
  };
  runInNewContext(source, {document, location: {origin: 'http://localhost'}, URL, Intl, AbortController,
    setTimeout(fn, delay) { const id = ++sequence; timers.set(id, {fn, delay}); return id; },
    clearTimeout(id) { timers.delete(id); },
    fetch(url, options) { return new Promise((resolve, reject) => requests.push({url, options, resolve, reject})); },
  });
  return {
    widget, list, requests, clicks,
    select(ids, frozen = false) { handlers['qr:cart-change'].forEach(fn => fn({detail: {ids, frozen}})); },
    startRequest() { const match = [...timers].find(([, timer]) => timer.delay === 160); assert.ok(match); timers.delete(match[0]); match[1].fn(); },
    async reply(index, items) { requests[index].resolve({ok: true, json: async () => ({items})}); await new Promise(resolve => setImmediate(resolve)); },
    async fail(index) { requests[index].reject(new Error('network')); await new Promise(resolve => setImmediate(resolve)); },
  };
}

test('stale response arriving during debounce cannot overwrite the new selection', async () => {
  const page = setup();
  page.select(['1']); page.startRequest();
  page.select(['2']);
  await page.reply(0, [{id: 3, name: 'Old', price: '20000'}]);
  assert.equal(page.widget.hidden, true);
  assert.equal(page.list.children.length, 0);
  page.startRequest();
  await page.reply(1, [{id: 4, name: 'Current', price: '30000'}]);
  assert.equal(page.widget.hidden, false);
  assert.equal(page.list.children[0].children[0].textContent, 'Current');
});

test('aborting an old request does not clear the pending signature', async () => {
  const page = setup();
  page.select(['1']); page.startRequest();
  page.select(['2']); await page.fail(0);
  page.startRequest(); await page.reply(1, [{id: 4, name: 'Current', price: '30000'}]);
  assert.equal(page.widget.hidden, false);
});

test('suggestion clicks reuse the existing add button and freeze with the cart', async () => {
  const page = setup();
  page.select(['1']); page.startRequest();
  await page.reply(0, [{id: 2, name: '<img onerror=bad()>', price: '10000'}]);
  const card = page.list.children[0], button = card.children[2];
  assert.equal(card.children[0].textContent, '<img onerror=bad()>');
  button.listeners.click(); assert.deepEqual(page.clicks, ['2']);
  page.select(['1'], true);
  button.listeners.click(); assert.deepEqual(page.clicks, ['2']);
  assert.equal(button.disabled, true);
});

test('empty cart hides suggestions and aborts an in-flight request', async () => {
  const page = setup();
  page.select(['1']); page.startRequest();
  page.select([]);
  assert.equal(page.requests[0].options.signal.aborted, true);
  await page.reply(0, [{id: 2, name: 'Old', price: '10000'}]);
  assert.equal(page.widget.hidden, true);
});
