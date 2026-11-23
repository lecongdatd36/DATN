/* Isolated localhost browser QA. Only the temporary browser's cart is changed. */
const { spawn } = require('node:child_process');
const { mkdir, readFile, writeFile } = require('node:fs/promises');
const path = require('node:path');
const { randomUUID } = require('node:crypto');
const base = process.argv[2] || 'http://127.0.0.1:8000';
if (new URL(base).hostname !== '127.0.0.1') throw Error('Localhost test server required');
const output = path.resolve('artifacts/homepage-preview/mobile-ux');
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
async function wait(fn, label, timeout = 20000) {
    const end = Date.now() + timeout;
    while (Date.now() < end) { if (await fn()) return; await sleep(100); }
    throw Error('Timed out: ' + label);
}
async function connect(url) {
    const socket = new WebSocket(url), tasks = new Map();
    let id = 0;
    await new Promise((resolve, reject) => {
        socket.addEventListener('open', resolve, { once: true });
        socket.addEventListener('error', reject, { once: true });
    });
    socket.addEventListener('message', event => {
        const result = JSON.parse(event.data), task = tasks.get(result.id);
        if (!task) return;
        tasks.delete(result.id); clearTimeout(task.timer);
        result.error ? task.reject(Error(result.error.message)) : task.resolve(result.result);
    });
    return { socket, call(method, params = {}) {
        return new Promise((resolve, reject) => {
            const key = ++id;
            const timer = setTimeout(() => { tasks.delete(key); reject(Error('CDP timeout: ' + method)); }, 25000);
            tasks.set(key, { resolve, reject, timer });
            socket.send(JSON.stringify({ id: key, method, params }));
        });
    } };
}
(async () => {
    await mkdir(output, { recursive: true });
    const profile = path.join(output, 'chrome-' + randomUUID());
    const environment = Object.fromEntries(Object.entries(process.env).filter(([key]) =>
        ['SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'PATH', 'USERPROFILE', 'LOCALAPPDATA', 'APPDATA', 'COMSPEC'].includes(key.toUpperCase())));
    const child = spawn('C:/Program Files/Google/Chrome/Application/chrome.exe', [
        '--headless=new', '--disable-gpu', '--no-first-run', '--disable-extensions',
        '--disable-background-networking', '--remote-debugging-port=0', '--user-data-dir=' + profile, 'about:blank',
    ], { windowsHide: true, stdio: 'ignore', env: environment });
    let page, browser;
    const results = [];
    try {
        let port;
        await wait(async () => {
            try { port = Number((await readFile(path.join(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0]); return port; }
            catch { return false; }
        }, 'Chrome startup');
        browser = await connect((await (await fetch(`http://127.0.0.1:${port}/json/version`)).json()).webSocketDebuggerUrl);
        const target = await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, { method: 'PUT' })).json();
        page = await connect(target.webSocketDebuggerUrl);
        await page.call('Page.enable'); await page.call('Network.enable');
        await page.call('Network.setCacheDisabled', { cacheDisabled: true });
        await page.call('Network.setCookie', { name: 'django_language', value: 'vi', url: base });
        await page.call('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: 'reduce' }] });
        const js = async expression => {
            const r = await page.call('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
            if (r.exceptionDetails) throw Error(JSON.stringify(r.exceptionDetails));
            return r.result?.value;
        };
        const assert = async (expression, label) => {
            if (!await js(expression)) throw Error(label + '\n' + await js(`JSON.stringify({url:location.href,width:innerWidth,scroll:document.documentElement.scrollWidth,overflow:[...document.querySelectorAll('body *')].filter(n=>{const r=n.getBoundingClientRect();return r.width>0&&(r.right>innerWidth+1||r.left< -1)}).slice(0,12).map(n=>n.tagName+'.'+n.className)})`));
        };
        const metrics = (width, height = 844) => page.call('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: width <= 760 });
        const nav = async route => {
            await page.call('Page.navigate', { url: base + route });
            await wait(() => js(`document.readyState==='complete'&&location.href.startsWith(${JSON.stringify(base + route)})&&!!document.querySelector('.cq-welcome')`), route);
            await js('document.fonts.ready');
            await js('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))');
        };
        const capture = async name => {
            const r = await page.call('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
            await writeFile(path.join(output, name + '.png'), Buffer.from(r.data, 'base64'));
        };
        const click = async selector => {
            const point = await js(`(()=>{const n=document.querySelector(${JSON.stringify(selector)});if(!n||n.disabled)throw Error('Missing control');n.scrollIntoView({block:'center',behavior:'instant'});const r=n.getBoundingClientRect(),x=r.x+r.width/2,y=r.y+r.height/2;if(!n.contains(document.elementFromPoint(x,y)))throw Error('Covered control: '+${JSON.stringify(selector)});return{x,y};})()`);
            await page.call('Input.dispatchMouseEvent', { type: 'mousePressed', ...point, button: 'left', clickCount: 1 });
            await page.call('Input.dispatchMouseEvent', { type: 'mouseReleased', ...point, button: 'left', clickCount: 1 });
        };
        const escape = async () => {
            await page.call('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 });
            await page.call('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 });
        };
        const layoutCheck = async (route, width) => {
            await nav(route);
            await assert('document.documentElement.scrollWidth <= innerWidth + 1', 'Page horizontal overflow');
            if (width <= 760) {
                await assert("!document.querySelector('[data-quick-booking-panel]').open", 'Booking must initially be collapsed');
                await assert("document.querySelector('.cq-welcome-visual').getBoundingClientRect().height>=document.querySelector('.cq-welcome-copy').getBoundingClientRect().height-1", 'Hero image must cover wrapped text');
                await assert("[...document.querySelectorAll('.cq-header-cart,.cq-header-toggle')].every(n=>{const r=n.getBoundingClientRect();return r.width>=44&&r.height>=44&&r.right<=innerWidth&&r.left>=0})", 'Header controls must fit and be touch sized');
                await assert("[...document.querySelectorAll('[data-basket-add=dish]:not(:disabled)')].filter(n=>n.getBoundingClientRect().width>0).every(n=>{const r=n.getBoundingClientRect();return r.width>=44&&r.height>=44})", 'Dish add controls too small');
                await assert("[...document.querySelectorAll('.cq-food-card,.cq-dish-card')].filter(n=>n.getBoundingClientRect().width>0).every(n=>n.scrollWidth<=n.clientWidth+1)", 'Dish card contents overflow');
                if (route === '/menu/') await assert("getComputedStyle(document.querySelector('.cq-catalog-grid')).gridTemplateColumns.split(' ').length===2", 'Phone menu must have two columns');
                else await assert("document.querySelector('.cq-food-card').getBoundingClientRect().top < 1000", 'Home dishes too far down');
            } else {
                await assert("document.querySelector('[data-quick-booking-panel]').open", 'Desktop booking form must stay expanded');
                await assert("getComputedStyle(document.querySelector('.cq-welcome-scene')).display==='contents'&&getComputedStyle(document.querySelector('.cq-quick-summary')).display==='none'", 'Desktop hero layout changed');
            }
            results.push({ route, width, language: await js('document.documentElement.lang'), layout: 'PASS' });
        };
        for (const width of [320, 360, 390, 430, 768, 1440]) {
            await metrics(width, width > 760 ? 1000 : 844);
            for (const route of ['/', '/menu/']) await layoutCheck(route, width);
            if (width <= 760) {
                await assert("document.documentElement.lang==='vi'", 'Vietnamese version did not load');
                await js('scrollTo(0,0)'); await capture('menu-top-' + width);
                await js("document.querySelector('#menu-catalog').scrollIntoView({behavior:'instant'})"); await capture('menu-dishes-' + width);
                await nav('/'); await capture('home-top-' + width);
            }
            if (width === 390) {
                await js("document.querySelector('#thuc-don').scrollIntoView({behavior:'instant'})"); await capture('home-dishes-390');
            }
            if (width === 1440) {
                await capture('desktop-menu');
                await nav('/'); await capture('desktop-home');
            }
        }
        await metrics(390); await nav('/');
        await click('.cq-quick-summary');
        await assert("document.querySelector('[data-quick-booking-panel]').open&&document.querySelector('[data-quick-booking]').getBoundingClientRect().height>0", 'Booking disclosure does not open');
        await js("(()=>{const f=document.querySelector('[data-quick-booking]'),day=new Date();day.setDate(day.getDate()+2);f.booking_date.value=day.toLocaleDateString('sv-SE');f.booking_time.value='18:30';f.party_size.value='6';f.requestSubmit()})()");
        await wait(() => js("document.readyState==='complete'&&location.pathname==='/reservations/online/'"), 'Quick booking navigation');
        await assert("document.querySelector('[name=party_size]').value==='6'&&document.querySelector('[name=starts_at]').value.endsWith('T18:30')", 'Collapsed quick booking must preserve form prefill');
        await nav('/');
        await click('[data-customer-menu-toggle]');
        await assert("document.querySelector('[data-customer-menu-toggle]').getAttribute('aria-expanded')==='true'&&document.querySelector('.cq-mobile-language').getBoundingClientRect().height>0", 'Phone navigation/language unavailable');
        await escape();
        await assert("document.querySelector('[data-customer-menu-toggle]').getAttribute('aria-expanded')==='false'&&document.activeElement.matches('[data-customer-menu-toggle]')", 'Escape must close menu and restore focus');
        await nav('/menu/');
        await js("document.querySelector('.customer-menu-filters a:last-child').scrollIntoView({block:'center',inline:'center',behavior:'instant'})");
        await click('.customer-menu-filters a:last-child');
        await wait(() => js("document.readyState==='complete'&&location.search.includes('category=')&&location.hash==='#menu-catalog'"), 'Category navigation');
        await js('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))');
        await assert('scrollY>100', 'Category navigation lost catalog scroll position');
        await assert("(()=>{const selected=document.querySelector('.customer-menu-filters [aria-current=true]'),nav=selected.parentElement,a=selected.getBoundingClientRect(),b=nav.getBoundingClientRect();return a.left>=b.left-1&&a.right<=b.right+1})()", 'Selected category must stay visible after navigation');
        const category = await js("new URL(location.href).searchParams.get('category')");
        const dishName = await js("document.querySelector('.cq-dish-content h2').textContent.trim()");
        await js(`document.querySelector('#dish-search').value=${JSON.stringify(dishName)};document.querySelector('.cq-catalog-toolbar form').requestSubmit()`);
        await wait(() => js(`document.readyState==='complete'&&new URL(location.href).searchParams.get('q')===${JSON.stringify(dishName)}`), 'Search navigation');
        await assert(`new URL(location.href).searchParams.get('category')===${JSON.stringify(category)}&&location.hash==='#menu-catalog'&&document.querySelector('.cq-dish-content h2').textContent.trim()===${JSON.stringify(dishName)}`, 'Search must retain category and catalog position');
        await click('[data-basket-add=dish]:not(:disabled)');
        await wait(() => js("document.body.classList.contains('cq-has-basket')"), 'Cart add');
        await assert("!document.querySelector('[data-basket-floating]').hidden&&document.querySelector('[data-basket-floating-total]').textContent===document.querySelector('[data-basket-total]').textContent", 'Cart summary total is missing');
        await js('scrollTo(0,0)'); await capture('menu-cart-bar-390');
        await nav('/');
        await wait(() => js("document.body.classList.contains('cq-has-basket')"), 'Cart persistence');
        await click('[data-basket-floating]');
        await assert("document.querySelector('[data-basket-dialog]').open&&[...document.querySelectorAll('[data-basket-plus],[data-basket-minus]')].every(n=>n.getBoundingClientRect().height>=44)", 'Basket controls inaccessible');
        await click('[data-basket-plus]');
        await wait(() => js("document.querySelector('[data-basket-count]').textContent==='2'"), 'Quantity increment');
        await capture('basket-390');
        await escape();
        await wait(() => js("!document.querySelector('[data-basket-dialog]').open&&!document.body.classList.contains('cq-basket-is-open')"), 'Basket close');
        await click('[data-basket-floating]'); await click('[data-basket-clear]');
        await wait(() => js("!document.body.classList.contains('cq-has-basket')"), 'Temporary cart cleanup');
        await escape();
        await page.call('Network.setCookie', { name: 'django_language', value: 'en', url: base });
        for (const width of [320, 390, 430]) {
            await metrics(width);
            for (const route of ['/', '/menu/']) await layoutCheck(route, width);
        }
        await metrics(390); await nav('/menu/');
        await assert("document.documentElement.lang==='en'", 'English version did not load');
        await js("document.querySelector('#menu-catalog').scrollIntoView({behavior:'instant'})"); await capture('menu-english-390');
        await writeFile(path.join(output, 'results.json'), JSON.stringify({ result: 'PASS', layouts: results, interactions: ['booking disclosure', 'navigation and Escape', 'category/search continuity', 'cart add/persistence/quantity/clear', 'VI and EN'], note: 'Temporary session cart only; no booking/order/payment submitted.' }, null, 2));
        console.log('PASS: ' + results.length + ' layouts, booking disclosure, navigation, filters, search, basket and English. Screenshots: ' + output);
    } finally {
        if (page) page.socket.close();
        if (browser) { try { await browser.call('Browser.close'); } catch {} browser.socket.close(); }
        if (child.exitCode === null) child.kill();
    }
})().catch(error => { console.error(error.stack); process.exitCode = 1; });
