const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

class Element {
    constructor(tag = 'div') { this.tag = tag; this.children = []; this.dataset = {}; this.listeners = {}; this.attributes = {}; this.hidden = false; this.disabled = false; this.value = ''; this.textContent = ''; }
    addEventListener(type, fn) { this.listeners[type] = fn; }
    async trigger(type, event = {}) { return this.listeners[type]?.({ preventDefault() {}, ...event }); }
    append(...children) { this.children.push(...children); }
    replaceChildren(...children) { this.children = children; }
    setAttribute(key, value) { this.attributes[key] = value; }
    focus() { this.focused = true; }
    querySelector(selector) { return this.selectors?.[selector]; }
    querySelectorAll() { return this.all || []; }
}

function harness(fetch) {
    const root = new Element(); root.dataset.endpoint = '/menu/chat/';
    const toggle = new Element('button');
    const panel = new Element('section'); panel.hidden = true;
    const close = new Element('button');
    const reset = new Element('button');
    const form = new Element('form');
    const input = new Element('textarea'); form.elements = { message: input };
    const send = new Element('button');
    const token = new Element('input'); token.value = 'test-csrf-token';
    form.selectors = { button: send, '[name=csrfmiddlewaretoken]': token };
    const status = new Element('p');
    const messages = new Element();
    const suggestions = new Element(); suggestions.all = [new Element('button')]; suggestions.all[0].textContent = 'Nhà hàng có món gì?';
    const scroller = new Element(); scroller.scrollHeight = 100;
    root.selectors = {
        '[data-chat-toggle]': toggle, '.customer-chat-panel': panel, '[data-chat-close]': close,
        '[data-chat-reset]': reset, '[data-chat-form]': form, '[data-chat-status]': status,
        '[data-chat-messages]': messages, '[data-chat-suggestions]': suggestions, '[data-chat-scroll]': scroller,
    };
    const created = [];
    const document = {
        querySelector: () => root,
        createElement(tag) { const element = new Element(tag); created.push(element); return element; },
        createTextNode(text) { return { nodeType: 3, textContent: text }; },
    };
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../static/customer/js/chatbot.js'), 'utf8'),
        { document, fetch, AbortController, window: { setTimeout, clearTimeout } });
    return { toggle, panel, close, reset, form, input, send, status, messages, suggestions, created };
}

function response(data, status = 200) {
    return { ok: status < 400, status, headers: { get: () => 'application/json' }, json: async () => data };
}
const settle = () => new Promise(resolve => setImmediate(resolve));

test('chat escapes AI text, sends CSRF, prevents duplicate sends, and resets without provider calls', async () => {
    const requests = [];
    let release;
    const pending = new Promise(resolve => { release = resolve; });
    const ui = harness(async (url, options) => {
        const payload = JSON.parse(options.body);
        requests.push({ url, options, payload });
        if (payload.action !== 'message') return response({ history: [], available: true });
        return pending;
    });
    await ui.toggle.trigger('click');
    assert.equal(ui.panel.hidden, false);
    ui.input.value = 'Có món gì?';
    const sending = ui.form.trigger('submit');
    assert.equal(ui.send.disabled, true);
    await ui.form.trigger('submit');
    assert.equal(requests.filter(item => item.payload.action === 'message').length, 1);
    const unsafe = '<img src=x onerror=alert(1)><script>bad()</script>';
    release(response({ answer: unsafe, dishes: [{ name: '<b>Món</b>', price_vnd: '65000', unit: 'Phần', category: 'Món chính' }], apriori: [], attempts: 1, max_turns: 12 }));
    await sending;
    await settle();
    assert.equal(ui.send.disabled, false);
    assert.equal(ui.messages.children.length, 2);
    assert.equal(ui.messages.children[1].children[1].nodeType, 3);
    assert.equal(ui.messages.children[1].children[1].textContent, unsafe);
    assert.equal(ui.created.some(element => ['img', 'script', 'b'].includes(element.tag)), false);
    const request = requests.find(item => item.payload.action === 'message');
    assert.equal(request.url, '/menu/chat/');
    assert.equal(request.options.credentials, 'same-origin');
    assert.equal(request.options.headers['X-CSRFToken'], 'test-csrf-token');
    assert.deepEqual(Object.keys(request.payload).sort(), ['action', 'message']);
    await ui.close.trigger('click');
    assert.equal(ui.panel.hidden, true);
    await ui.toggle.trigger('click');
    await ui.reset.trigger('click');
    await settle();
    assert.equal(ui.messages.children.length, 0);
    assert.equal(requests.filter(item => item.payload.action === 'message').length, 1);
});

test('quota errors remain plain text and restore the composer', async () => {
    const ui = harness(async (url, options) => JSON.parse(options.body).action === 'state'
        ? response({ history: [], available: true })
        : response({ error: 'Gemini đã hết hạn mức. Vui lòng thử lại sau.' }, 429));
    await ui.toggle.trigger('click');
    ui.input.value = 'Tư vấn món';
    await ui.form.trigger('submit');
    await settle();
    assert.match(ui.status.textContent, /hết hạn mức/);
    assert.equal(ui.send.disabled, false);
    assert.equal(ui.input.disabled, false);
    assert.equal(ui.input.value, 'Tư vấn món');
    assert.equal(ui.messages.children.length, 0);
});
