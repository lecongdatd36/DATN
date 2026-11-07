const {spawn} = require('node:child_process');
const {readFile, writeFile} = require('node:fs/promises');
const path = require('node:path');
const [baseUrl, profile, output] = process.argv.slice(2);
if (new URL(baseUrl).hostname !== '127.0.0.1') throw Error('Local test server only');
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
async function connect(url) {
  const socket = new WebSocket(url), pending = new Map(); let sequence = 0;
  await new Promise((resolve, reject) => {socket.addEventListener('open', resolve, {once:true}); socket.addEventListener('error', reject, {once:true});});
  socket.addEventListener('message', event => {
    const message = JSON.parse(event.data), request = pending.get(message.id);
    if (!request) return; pending.delete(message.id);
    if (message.error) request.reject(Error(message.error.message)); else request.resolve(message.result);
  });
  return {socket, call(method, params={}) {return new Promise((resolve,reject) => {const id=++sequence;pending.set(id,{resolve,reject});socket.send(JSON.stringify({id,method,params}));});}};
}
async function until(fn, timeout=10000) {
  const deadline = Date.now()+timeout;
  while (Date.now()<deadline) {const result = await fn(); if(result) return result; await sleep(80);}
  throw Error('Browser check timed out');
}
(async () => {
  const routes = await (await fetch(baseUrl+'/__management_test__/routes')).json();
  const child = spawn('C:/Program Files/Google/Chrome/Application/chrome.exe', [
    '--headless=new','--no-sandbox','--disable-gpu','--no-first-run','--disable-background-networking',
    '--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'
  ], {windowsHide:true, stdio:'ignore'});
  let browser, page;
  const checks=[];
    const layouts={};
  const assert = (condition, message) => {if(!condition) throw Error(message);checks.push(message);};
  try {
    const port = await until(async()=>{try{return Number((await readFile(path.join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0]);}catch{return null;}});
    browser = await connect((await (await fetch(`http://127.0.0.1:${port}/json/version`)).json()).webSocketDebuggerUrl);
    const target = await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`,{method:'PUT'})).json();
    page = await connect(target.webSocketDebuggerUrl); await page.call('Page.enable');
    const evaluate = async expression => {
      const response = await page.call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
      if(response.exceptionDetails) throw Error(JSON.stringify(response.exceptionDetails));
      return response.result?.value;
    };
    const go = async route => {
      await page.call('Page.navigate',{url:baseUrl+route});
      await until(()=>evaluate(`location.pathname === (${JSON.stringify(route.split('?')[0])} === ${JSON.stringify(routes['seating:table_list'])} && matchMedia('(max-width: 767.98px)').matches ? ${JSON.stringify(routes['sales:mobile'])} : ${JSON.stringify(route.split('?')[0])}) && document.readyState === 'complete'`));
    };
    const resize = async width => {await page.call('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:width<768});};
    const capture = async name => {await writeFile(path.join(output,name+'.png'), Buffer.from((await page.call('Page.captureScreenshot',{format:'png',captureBeyondViewport:false})).data,'base64'));};
    const login = async (role, width, expected, next='') => {
      await page.call('Network.clearBrowserCookies'); await resize(width);
      await go(routes['accounts:login']+(next?'?next='+encodeURIComponent(next):''));
      assert(await evaluate(`document.querySelector('[data-mobile-login]').value === '${width<768?1:0}'`), `${role} ${width}px login detects device`);
      if(width<768) {
        assert(await evaluate(`getComputedStyle(document.body).backgroundColor === 'rgb(255, 255, 255)' && getComputedStyle(document.querySelector('.cq-login-form .customer-button')).backgroundColor === 'rgb(200, 16, 46)'`), `${role} login uses shared white and red theme`);
        if(role==='manager') await capture('login-mobile');
      }
      await evaluate(`document.querySelector('[name=username]').value=${JSON.stringify('browser-'+role)};document.querySelector('[name=password]').value='Browser-test-only-123';document.querySelector('form.cq-login-form').requestSubmit();`);
      await until(()=>evaluate(`location.pathname === ${JSON.stringify(routes[expected])} && document.readyState === 'complete'`));
      assert(true, `${role} ${width}px reaches ${expected}`);
    };
    await login('manager',390,'accounts:workspace');
    for(const width of [320,390,767,1440]) {
      await resize(width);
      for(const name of ['accounts:workspace','inventory:daily_usage','inventory:workspace','bookings:create','bookings:settings','bookings:list','seating:table_list','menu:dish_list','customers:customer_list','accounts:account_list','employees:employee_list','reports:dashboard','kitchen:workspace','mobile:tables','mobile:menu','mobile:order','mobile:checkout','mobile:tasks','mobile:personal']) {
        await go(routes[name]);
        assert(await evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), `${name} ${width}px fits viewport`);
        if(width<768 || name.startsWith('mobile:')) {
          assert(await evaluate(`(() => {const rect=document.querySelector('.m-header, .admin-topbar').getBoundingClientRect();return rect.top === 0 && rect.height === 80;})()`), `${name} ${width}px shares 80px header without top gap`);
          assert(await evaluate(`getComputedStyle(document.body).backgroundColor === 'rgb(255, 255, 255)'`), `${name} ${width}px uses white background`);
          assert(await evaluate(`getComputedStyle(document.documentElement).getPropertyValue('--app-primary').trim() === '#c8102e'`), `${name} ${width}px shares red primary color`);
          const warm = await evaluate(`(() => {
            const matches=[];
            for(const el of document.querySelectorAll('body *')) {
              if(!el.getClientRects().length || ['SCRIPT','STYLE','SVG','PATH','USE'].includes(el.tagName)) continue;
              const style=getComputedStyle(el);
              for(const key of ['color','backgroundColor','borderTopColor']) {
                const rgb=style[key].match(/^rgba?\\((\\d+), (\\d+), (\\d+)(?:, ([\\d.]+))?\\)/);
                if(!rgb || (rgb[4] && Number(rgb[4])<.1)) continue;
                const [r,g,b]=rgb.slice(1,4).map(Number);
                if(r>g+14 && g>b+12 && (r-b)>35) matches.push(el.tagName+'.'+el.className+':'+key+'='+style[key]);
              }
            }
            return [...new Set(matches)].slice(0,10);
          })()`);
          assert(warm.length===0, `${name} ${width}px has no orange or brown component colors ${warm.join('; ')}`);
        }
        if(name==='accounts:workspace') {
          if(width<768) {
            assert(await evaluate(`getComputedStyle(document.querySelector('.admin-sidebar')).boxShadow === 'none' && getComputedStyle(document.querySelector('.message-stack')).display === 'none'`), `${width}px management has no sidebar shadow or empty message gap`);
          }
          assert(await evaluate(`getComputedStyle(document.querySelector(innerWidth<768?'.management-mobile-header':'.admin-topbar')).display !== 'none'`), `${width}px header shows current page title`);
          const visible = await evaluate(`getComputedStyle(document.querySelector('.mobile-app-nav')).display !== 'none'`);
          assert(visible===(width<768), `${width}px displays matching management navigation`);
          const salesHref=await evaluate(`new URL(document.querySelector('[data-device-sales-link]').href).pathname`);
          assert(salesHref===routes[width<768?'sales:mobile':'sales:workspace'], `${width}px Order shortcut selects matching workspace`);
        }
        if(width===390) {
          layouts[name]=await evaluate(`({header: document.querySelector('.m-header, .admin-topbar')?.getBoundingClientRect().toJSON(), children: [...document.querySelectorAll('.m-shell > *, .m-page > *')].slice(0,9).map(el=>({tag:el.tagName,cls:el.className,hidden:el.hidden,display:getComputedStyle(el).display,rect:el.getBoundingClientRect().toJSON(),text:el.textContent.trim().slice(0,80)}))})`);
          await capture(name.replace(':','-')+'-mobile');
        }
        if(width===1440 && name==='accounts:workspace') await capture('management-desktop');
      }
    }
    await resize(390); await go(routes['accounts:workspace']);
    const shellSignature = () => evaluate(`JSON.stringify({header:document.querySelector('.m-header').textContent.trim().replace(/\\s+/g,' '),nav:[...document.querySelector('.m-nav').querySelectorAll('a')].map(a=>({href:new URL(a.href).pathname+new URL(a.href).search,label:a.querySelector('span')?.textContent})),height:document.querySelector('.m-header').getBoundingClientRect().height})`);
    const managementShell = await shellSignature();
    await evaluate(`document.querySelector('.m-nav a[href*="page=personal"]').click()`);
    await until(()=>evaluate(`location.pathname === ${JSON.stringify(routes['sales:mobile'])} && document.querySelector('[data-page="personal"]') && document.readyState==='complete'`));
    assert(await evaluate(`Boolean(document.querySelector('.m-management-links a[href=${JSON.stringify(routes['bookings:settings'])}]'))`), 'Shared More page keeps management functions accessible');
    await capture('management-functions-mobile');
    await go(routes['seating:table_list']);
    assert(await evaluate(`location.pathname === ${JSON.stringify(routes['sales:mobile'])} && Boolean(document.querySelector('.m-table-grid')) && !document.querySelector('[data-mobile-table-page]')`), 'Phone /ban/ resolves to the actual Order table screen');
    await capture('tables-from-management');
    const tableSignature = () => evaluate(`(() => {const copy=document.querySelector('.m-table-grid').cloneNode(true);copy.querySelectorAll('[name=csrfmiddlewaretoken]').forEach(node=>node.remove());return copy.innerHTML;})()`);
    const tableMarkup = await tableSignature();
    await go(routes['mobile:tables']);
    assert(await tableSignature() === tableMarkup, 'Both table entry points render identical table cards and actions');
    const orderShell = await shellSignature();
    const first=JSON.parse(managementShell), second=JSON.parse(orderShell);
    assert(JSON.stringify(first.nav)===JSON.stringify(second.nav) && first.height===second.height, 'Management and Order use the same role navigation and header geometry');
    await capture('tables-from-order');
    await go(routes['kitchen:workspace']);
    await evaluate(`document.querySelector('[data-kitchen-tab="cooking"]').click()`);
    assert(await evaluate(`getComputedStyle(document.querySelector('[data-kitchen-panel="pending"]')).display === 'none' && getComputedStyle(document.querySelector('[data-kitchen-panel="cooking"]')).display !== 'none'`), 'Kitchen mobile tabs show only the selected panel');
    await capture('kitchen-cooking-mobile');
    await go(routes['mobile:tables']);
    await evaluate(`document.querySelector('[data-mobile-notification-open]').click()`);
    assert(await evaluate(`getComputedStyle(document.querySelector('[data-mobile-notification-panel]')).backgroundColor === 'rgb(255, 255, 255)'`), 'Order notification dialog uses white background');
    await capture('order-notifications-mobile');
    await go(routes['bookings:create']);
    await evaluate(`document.querySelector('[name=starts_at]').value='2099-01-01T03:00';document.querySelector('[name=party_size]').value='2';document.querySelector('[name=duration_minutes]').value='120';document.querySelector('main form[method=post]').requestSubmit();`);
    await until(()=>evaluate(`document.readyState==='complete' && document.body.innerText.includes('09:00') && Boolean(document.querySelector('.invalid-feedback'))`));
    assert(await evaluate(`document.body.innerText.includes('22:00')`), 'Night booking submission displays business hours error');
    await login('manager',1440,'accounts:workspace');
    for(const role of ['waiter','cashier']) {
      await login(role,390,'sales:mobile',routes['sales:workspace']);
      await login(role,1440,'sales:workspace',routes['sales:mobile']);
    }
    await login('inventory',390,'inventory:workspace');
    await login('kitchen',390,'kitchen:workspace');
    const report=`${checks.length} browser checks passed\n`+checks.join('\n');
    await writeFile(path.join(output,'checks.txt'), report, 'utf8');
    await writeFile(path.join(output,'layouts.json'), JSON.stringify(layouts,null,2), 'utf8');
    process.stdout.write(report+'\n');
  } finally {
    if(page) page.socket.close();
    if(browser) {try{await Promise.race([browser.call('Browser.close'),sleep(2000)]);}catch{}browser.socket.close();}
    if(child.exitCode===null) child.kill();
  }
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
