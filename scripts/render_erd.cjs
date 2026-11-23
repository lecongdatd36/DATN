/* Render metadata-generated DOT as SVG and PNG without sending schema to a service.
   Usage: node scripts/render_erd.cjs /path/to/@viz-js/viz [docs/use-case]
   Requires an existing Chrome installation on Windows. */
const fs = require('node:fs/promises');
const path = require('node:path');
const {spawn} = require('node:child_process');
const root = path.resolve(__dirname, '..');
const out = path.resolve(root, process.argv[3] || 'docs/erd');
if (!out.startsWith(root + path.sep)) throw Error('Output folder must be inside this workspace');
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));

async function until(fn) {
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) {
    const result = await fn();
    if (result) return result;
    await wait(80);
  }
  throw Error('Chrome startup timed out');
}

async function connect(url) {
  const socket = new WebSocket(url), pending = new Map();
  let id = 0;
  await new Promise((resolve, reject) => {
    socket.addEventListener('open', resolve, {once:true});
    socket.addEventListener('error', reject, {once:true});
  });
  socket.addEventListener('message', event => {
    const message = JSON.parse(event.data), item = pending.get(message.id);
    if (!item) return;
    pending.delete(message.id);
    if (message.error) item.reject(Error(message.error.message));
    else item.resolve(message.result);
  });
  return {socket, call(method, params={}) {
    return new Promise((resolve, reject) => {
      const sequence = ++id;
      pending.set(sequence, {resolve, reject});
      socket.send(JSON.stringify({id:sequence, method, params}));
    });
  }};
}

(async () => {
  const modulePath = process.argv[2];
  if (!modulePath) throw Error('Provide the installed @viz-js/viz module path');
  const viz = await require(path.resolve(modulePath)).instance();
  const stems = process.argv[3]
    ? (await fs.readdir(out)).filter(name => name.endsWith('.dot')).map(name => name.slice(0, -4))
    : ['erd-tong-quan', 'erd-day-du'];
  function umlActors(svg) {
    return svg.replace(/<g id="actor__[^\"]+" class="node">[\s\S]*?<\/g>/g, group => {
      const title = group.match(/<title>[\s\S]*?<\/title>/)[0];
      const coordinates = group.match(/<polygon[^>]+points="([^"]+)"/)[1].trim().split(/\s+/).map(pair => pair.split(',').map(Number));
      const xs=coordinates.map(p=>p[0]), ys=coordinates.map(p=>p[1]);
      const x=(Math.min(...xs)+Math.max(...xs))/2, top=Math.min(...ys)+4;
      const lines=[...group.matchAll(/<text[^>]*>([\s\S]*?)<\/text>/g)].map(match=>match[1]);
      const person=`<g fill="none" stroke="#182230" stroke-width="1.8"><circle cx="${x}" cy="${top+10}" r="8"/><path d="M${x},${top+18}V${top+48}M${x-18},${top+29}H${x+18}M${x},${top+48}L${x-17},${top+68}M${x},${top+48}L${x+17},${top+68}"/></g>`;
      const text=lines.map((line,i)=>`<text x="${x}" y="${top+87+i*16}" text-anchor="middle" font-family="Arial" font-size="13" fill="#182230">${line}</text>`).join('');
      return group.slice(0,group.indexOf('>')+1)+title+person+text+'</g>';
    });
  }
  for (const stem of stems) {
    const dot = await fs.readFile(path.join(out, stem + '.dot'), 'utf8');
    const result = viz.render(dot, {format:'svg', engine:'dot'});
    const errors = result.errors.filter(item => item.level === 'error');
    if (result.status !== 'success' || errors.length) throw Error(JSON.stringify(errors));
    await fs.writeFile(path.join(out, stem + '.svg'), umlActors(result.output));
  }
  const profile = await fs.mkdtemp(path.join(root, 'artifacts', 'ai', 'erd-render-'));
  const child = spawn('C:/Program Files/Google/Chrome/Application/chrome.exe', [
    '--headless=new', '--no-sandbox', '--disable-gpu', '--no-first-run', '--disable-background-networking',
    '--remote-debugging-port=0', '--user-data-dir=' + profile, 'about:blank'
  ], {windowsHide:true, stdio:'ignore'});
  let browser, page;
  try {
    const port = await until(async () => {
      try { return Number((await fs.readFile(path.join(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0]); }
      catch { return null; }
    });
    browser = await connect((await (await fetch(`http://127.0.0.1:${port}/json/version`)).json()).webSocketDebuggerUrl);
    const tab = await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, {method:'PUT'})).json();
    page = await connect(tab.webSocketDebuggerUrl);
    for (const stem of stems) {
      const svg = await fs.readFile(path.join(out, stem + '.svg'), 'utf8');
      const viewBox = svg.match(/viewBox="([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+)"/).slice(1).map(Number);
      const scale = Math.min(2, 10000 / Math.max(viewBox[2], viewBox[3]));
      for (const [suffix, imageScale] of [['', scale], ['-preview', Math.min(1, 1800 / viewBox[2])]]) {
        const width = Math.ceil(viewBox[2] * imageScale), height = Math.ceil(viewBox[3] * imageScale);
        const expression = `(async()=>{
          const img = new Image();
          img.src=${JSON.stringify('data:image/svg+xml;base64,' + Buffer.from(svg).toString('base64'))};
          await img.decode();
          const canvas=document.createElement('canvas');canvas.width=${width};canvas.height=${height};
          const context=canvas.getContext('2d');context.fillStyle='white';context.fillRect(0,0,canvas.width,canvas.height);
          context.drawImage(img,0,0,canvas.width,canvas.height);
          return canvas.toDataURL('image/png').split(',')[1];
        })()`;
        const result = await page.call('Runtime.evaluate', {expression, returnByValue:true, awaitPromise:true});
        if (result.exceptionDetails) throw Error(JSON.stringify(result.exceptionDetails));
        await fs.writeFile(path.join(out, stem + suffix + '.png'), Buffer.from(result.result.value, 'base64'));
        console.log(`${stem}${suffix}.png ${width}x${height}`);
      }
    }
  } finally {
    if (browser) { try { await browser.call('Browser.close'); } catch {} browser.socket.close(); }
    if (page) page.socket.close();
    child.kill();
  }
})().catch(error => { console.error(error); process.exitCode=1; });
