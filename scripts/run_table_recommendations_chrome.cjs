// Isolated Chrome; only navigates the disposable local booking-test server.
const {spawn} = require('node:child_process');
const {readFile, writeFile} = require('node:fs/promises');
const path = require('node:path');
const [baseUrl, profile, output] = process.argv.slice(2);
if (new URL(baseUrl).hostname !== '127.0.0.1') throw Error('Only the local test server is supported');
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
async function connect(url) {
  const socket = new WebSocket(url), pending = new Map(); let sequence = 0;
  await new Promise((resolve, reject) => {
    socket.addEventListener('open', resolve, {once: true});
    socket.addEventListener('error', reject, {once: true});
  });
  socket.addEventListener('message', event => {
    const message = JSON.parse(event.data), request = pending.get(message.id);
    if (!request) return;
    pending.delete(message.id);
    if (message.error) request.reject(Error(message.error.message)); else request.resolve(message.result);
  });
  return {socket, call(method, params = {}) {
    return new Promise((resolve, reject) => {
      const id = ++sequence; pending.set(id, {resolve, reject});
      socket.send(JSON.stringify({id, method, params}));
    });
  }};
}
async function waitUntil(callback, timeout = 12000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) {const value = await callback(); if (value) return value; await sleep(80);}
  throw Error('Browser check timed out');
}
(async () => {
  const child = spawn('C:/Program Files/Google/Chrome/Application/chrome.exe', [
    '--headless=new', '--no-sandbox', '--disable-gpu', '--no-first-run', '--hide-scrollbars',
    '--disable-background-networking', '--remote-debugging-port=0', '--user-data-dir=' + profile, 'about:blank',
  ], {windowsHide: true, stdio: 'ignore'});
  let browser, page;
  const checks = [];
  try {
    const port = await waitUntil(async () => {
      try {return Number((await readFile(path.join(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0]);}
      catch {return null;}
    });
    const info = await (await fetch(`http://127.0.0.1:${port}/json/version`)).json();
    browser = await connect(info.webSocketDebuggerUrl);
    const target = await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, {method: 'PUT'})).json();
    page = await connect(target.webSocketDebuggerUrl);
    await page.call('Page.enable');
    const evaluate = async expression => {
      const result = await page.call('Runtime.evaluate', {expression, returnByValue: true, awaitPromise: true});
      if (result.exceptionDetails) throw Error(result.exceptionDetails.text);
      return result.result?.value;
    };
    const check = (value, label) => {if (!value) throw Error(label); checks.push(label);};
    const viewport = width => page.call('Emulation.setDeviceMetricsOverride', {width, height: 900, deviceScaleFactor: 1, mobile: false});
    const navigate = async (name, selector) => {
      await page.call('Page.navigate', {url: baseUrl + '/__table_test__/' + name});
      await waitUntil(() => evaluate(`document.readyState === 'complete' && Boolean(document.querySelector(${JSON.stringify(selector)}))`));
      await evaluate('document.fonts.ready.then(() => true)');
    };
    const capture = async name => {
      const shot = await page.call('Page.captureScreenshot', {format: 'png', captureBeyondViewport: false});
      await writeFile(path.join(output, name + '.png'), Buffer.from(shot.data, 'base64'));
    };
    await viewport(1440);
    await navigate('staff', '[data-table-best]');
    check(await evaluate(`document.querySelector('[data-table-best]').textContent.includes('Z04')`), 'Staff best-fit table is Z04');
    check(await evaluate(`document.querySelector('tbody tr').textContent.includes('Z04') && document.querySelector('tbody tr').textContent.includes('75')`), 'Staff first row shows rank, score and best-fit table');
    check(await evaluate(`new URL(document.querySelector('tbody a').href).searchParams.get('party_size') === '3'`), 'Staff selection preserves party size');
    await capture('staff-desktop');
    await viewport(390);
    await evaluate(`document.querySelector('[data-table-best]').scrollIntoView({block:'start'})`);
    check(await evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), 'Staff mobile has no page-wide horizontal overflow');
    await capture('staff-mobile');
    await viewport(1440);
    await navigate('public', '[data-table-recommendation]');
    check(await evaluate(`document.querySelector('[data-table-recommendation]').textContent.includes('Z04') && document.querySelectorAll('[data-table-recommendation]').length === 2`), 'Public page shows ranked eligible tables');
    await evaluate(`document.querySelector('.customer-result-card').scrollIntoView({block:'center'})`);
    await capture('public-desktop');
    await viewport(390);
    await evaluate(`document.querySelector('.customer-result-card').scrollIntoView({block:'start'})`);
    check(await evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), 'Public mobile has no page-wide horizontal overflow');
    await capture('public-mobile');
    await evaluate(`document.querySelector('.customer-result-card .customer-button').click()`);
    await waitUntil(() => evaluate(`document.readyState === 'complete' && Boolean(document.querySelector('input[name="full_name"]'))`));
    check(await evaluate(`document.querySelector('[name="party_size"]').value === '3' && !document.querySelector('[name="duration_minutes"]') && Boolean(document.querySelector('[name="starts_at"]').value)`), 'Continue booking preserves time and party size without a public duration input');
    await navigate('empty', '.customer-result-card');
    check(await evaluate(`!document.querySelector('[data-table-recommendation]') && document.querySelector('.customer-result-card').textContent.includes('Chưa có bàn phù hợp')`), 'No-capacity result has no misleading recommendation');
    await navigate('late', '[data-duration-preview]');
    check(await evaluate(`document.querySelector('[data-duration-preview]').textContent.includes('60 phút') && document.querySelector('[data-duration-preview]').textContent.includes('22:00')`), 'Public 21:00 arrival previews 60 minutes and closing time');
    await capture('booking-public-late-mobile');
    await navigate('midnight', '.customer-field-error');
    check(await evaluate(`document.querySelector('.customer-field-error').textContent.includes('08:00') && !document.querySelector('.customer-result-card')`), 'Midnight search is rejected by the server');
    await viewport(1440);
    await navigate('booking', '[data-booking-form]');
    await waitUntil(() => evaluate(`document.querySelector('[data-booking-customer-result]').textContent.includes('Private customer') && document.querySelector('[name="table"]').options.length === 3`));
    check(await evaluate(`document.querySelector('[data-new-customer]').hidden`), 'Known phone displays customer name and hides new-customer input');
    check(await evaluate(`document.querySelector('[data-booking-summary]').textContent.includes('60 phút') && document.querySelector('[name="table"]').value !== ''`), 'Staff summary preserves selected table and shortened duration');
    await capture('booking-staff-late-desktop');
    await evaluate(`(() => {const input = document.querySelector('[name="customer_phone"]'); input.value = '0901234567'; input.dispatchEvent(new Event('input', {bubbles:true}));})()`);
    await waitUntil(() => evaluate(`document.querySelector('[data-booking-customer-result]').textContent.includes('Khách mới')`));
    check(await evaluate(`!document.querySelector('[data-new-customer]').hidden && !document.querySelector('[data-booking-summary]').textContent.includes('Private customer')`), 'Changing phone clears stale identity and offers inline customer creation');
    await evaluate(`(() => {const input = document.querySelector('[name="party_size"]'); input.value = '100'; input.dispatchEvent(new Event('input', {bubbles:true}));})()`);
    await waitUntil(() => evaluate(`document.querySelector('[data-booking-tables-result]').textContent.includes('Hết bàn')`));
    check(await evaluate(`document.querySelector('[name="table"]').value === '' && document.querySelector('[name="table"]').options.length === 1`), 'Party-size change removes tables that no longer fit');
    await viewport(390);
    check(await evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), 'Booking form has no horizontal overflow on mobile');
    await capture('booking-staff-mobile');
    const report = JSON.stringify({passed: checks.length, checks}, null, 2);
    await writeFile(path.join(output, 'checks.json'), report, 'utf8');
    process.stdout.write(report + '\n');
  } finally {
    if (page) page.socket.close();
    if (browser) {try {await Promise.race([browser.call('Browser.close'), sleep(2000)]);} catch {} browser.socket.close();}
    if (child.exitCode === null) child.kill();
  }
})().catch(error => {console.error(error.message); process.exitCode = 1;});
