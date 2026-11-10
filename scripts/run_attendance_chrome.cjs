const {spawn} = require('node:child_process');
const {readFile, writeFile} = require('node:fs/promises');
const path = require('node:path');
const [base, profile, output] = process.argv.slice(2);
if (new URL(base).hostname !== '127.0.0.1') throw Error('Local disposable test server only');
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
async function wait(fn, timeout=15000) { const end=Date.now()+timeout; while(Date.now()<end) { const value=await fn(); if(value)return value; await sleep(100); } throw Error('Browser check timed out'); }
async function connect(url) {
  const socket=new WebSocket(url), pending=new Map(); let id=0;
  await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
  socket.addEventListener('message', event=>{const data=JSON.parse(event.data), task=pending.get(data.id); if(!task)return; pending.delete(data.id); data.error?task.reject(Error(data.error.message)):task.resolve(data.result);});
  return {socket, call(method,params={}) { return new Promise((resolve,reject)=>{const key=++id; pending.set(key,{resolve,reject}); socket.send(JSON.stringify({id:key,method,params}));}); }};
}
(async()=>{
  const child=spawn('C:/Program Files/Google/Chrome/Application/chrome.exe', ['--headless=new','--no-sandbox','--disable-gpu','--no-first-run','--disable-background-networking','--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'], {windowsHide:true,stdio:'ignore'});
  let page,browser;
  try {
    const port=await wait(async()=>{try{return Number((await readFile(path.join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0]);}catch{return null;}});
    browser=await connect((await (await fetch(`http://127.0.0.1:${port}/json/version`)).json()).webSocketDebuggerUrl);
    const target=await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`,{method:'PUT'})).json();
    page=await connect(target.webSocketDebuggerUrl); await page.call('Page.enable');
    const errors=[]; page.socket.addEventListener('message', event=>{const data=JSON.parse(event.data);if(data.method==='Runtime.exceptionThrown')errors.push(data.params.exceptionDetails.text);});
    await page.call('Runtime.enable');
    const js=async expression=>{const result=await page.call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(result.exceptionDetails)throw Error(result.exceptionDetails.text);return result.result?.value;};
    const navigate=async route=>{await page.call('Page.navigate',{url:base+route});await wait(()=>js(`document.readyState==='complete' && location.pathname===${JSON.stringify(route.split('?')[0])}`));};
    const metrics=async(width,height)=>page.call('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});
    const capture=async name=>{const result=await page.call('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await writeFile(path.join(output,name+'.png'),Buffer.from(result.data,'base64'));};
    const assert=async(expression,message)=>{if(!await js(expression))throw Error(message);};
    const config=await (await fetch(base+'/__workforce_test__/config')).json();
    await metrics(1440,1000);
    await page.call('Page.navigate',{url:base+'/__workforce_test__/manager'});
    await wait(()=>js("document.readyState==='complete' && Boolean(document.querySelector('#id_code'))"));
    await js(`(()=>{const form=document.querySelector('#id_code').form;form.code.value='BROWSER';form.name.value='Ca thử trên trình duyệt';form.starts_at.value='10:00';form.ends_at.value='16:00';form.break_minutes.value='30';form.grace_minutes.value='5';form.is_active.checked=true;form.requestSubmit();})()`);
    await wait(()=>js("document.readyState==='complete' && document.querySelector('tbody')?.textContent.includes('BROWSER')"));
    await capture('shifts-desktop');
    await navigate('/cham-cong/');
    await js(`(()=>{const form=document.querySelector('#id_employees').form;[...form.employees.options].forEach(option=>option.selected=option.value===${JSON.stringify(String(config.employee))});form.shift.value=[...form.shift.options].find(option=>option.textContent.includes('BROWSER')).value;form.work_date.value=${JSON.stringify(config.day)};form.requestSubmit();})()`);
    await wait(()=>js("document.readyState==='complete' && Boolean(document.querySelector('button[value=publish]'))"));
    await js("document.querySelector('button[value=publish]').click()");
    await wait(()=>js("document.readyState==='complete' && document.querySelector('tbody')?.textContent.includes('Đã công bố')"));
    await capture('schedules-desktop');
    await metrics(390,844); await capture('schedules-mobile');
    await assert('document.documentElement.scrollWidth <= innerWidth+1', 'Schedule page overflows mobile viewport');
    await navigate(`/cham-cong/bang-cong/?start=${config.day}&end=${config.day}`);
    await capture('timesheet-mobile');
    await assert('document.documentElement.scrollWidth <= innerWidth+1', 'Timesheet overflows mobile viewport');
    await metrics(1440,1000);
    await navigate(`/cham-cong/khuon-mat/${config.employee}/`);
    await js("document.querySelector('[data-camera-start]').click()");
    await wait(()=>js("!document.querySelector('[data-capture]').disabled"));
    for(let index=0;index<3;index++){await js("document.querySelector('[data-capture]').click()");await sleep(1200);}
    await js("document.querySelector('#face-consent').checked=true;document.querySelector('[data-save]').click()");
    await wait(()=>js("document.querySelector('.wf-camera-status').textContent.includes('Chỉ một người')"));
    await capture('enrollment-invalid-camera');
    await page.call('Network.enable');
    await page.call('Network.clearBrowserCookies');
    await navigate('/cham-cong/diem-cham-cong/');
    await assert("document.body.textContent.includes('không cần đăng nhập') && !document.body.textContent.includes('Kích hoạt')", 'Shared page must work without activating a device');
    await capture('shared-point-desktop');
    await js("document.querySelector('[data-clock-action=IN]').click()");
    await wait(()=>js("document.querySelector('.wf-camera-status').textContent.includes('Chỉ một người')"),25000);
    await js("document.querySelector('[data-cancel]').click()");
    await metrics(390,844); await capture('shared-point-mobile');
    await assert('document.documentElement.scrollWidth <= innerWidth+1', 'Kiosk overflows mobile viewport');
    await fetch(base+'/__workforce_test__/face-mode/known',{method:'POST'});
    await sleep(3200);
    await js("document.querySelector('[data-clock-action=IN]').click()");
    await wait(()=>js("document.querySelector('.wf-camera-status').textContent.includes('Chưa có lịch ca')"));
    await assert("document.querySelector('[data-person]').textContent==='Nhân viên khác' && document.querySelector('[data-identity]').textContent.includes('chưa ghi công')", 'Identified face without a shift must explain why attendance is not recorded');
    await capture('identified-without-shift-mobile');
    await sleep(3200);
    await fetch(base+'/__workforce_test__/face-mode/known-clock',{method:'POST'});
    await js("document.querySelector('[data-clock-action=IN]').click()");
    await wait(()=>js("document.querySelector('[data-identity]').textContent==='Đã ghi công thành công'"),20000);
    await capture('shared-point-clock-in-success');
    await js("document.querySelector('[data-clock-action=OUT]').click()");
    await wait(()=>js("document.querySelector('.wf-camera-status').textContent.includes('Ra ca thành công')"),20000);
    await capture('shared-point-clock-out-success');
    await page.call('Page.navigate',{url:base+'/cham-cong/'});
    await wait(()=>js("document.readyState==='complete' && location.pathname.includes('dang-nhap')"));
    await assert("!document.querySelector('.wf-page')", 'Kiosk must not retain manager access');
    if(errors.length)throw Error(errors.join('\n'));
    const report='ATTENDANCE BROWSER CHECKS PASSED\nReal forms and shared anonymous page. Fake camera enrollment rejected; known-face fixture without shift shows a clear reason; synthetic inference completes real IN/OUT challenge and ledger. No device activation. Mobile pages fit viewport.\n';
    await writeFile(path.join(output,'checks.txt'),report); process.stdout.write(report);
  } finally {
    if(page)page.socket.close();
    if(browser){try{await Promise.race([browser.call('Browser.close'),sleep(2000)]);}catch{}browser.socket.close();}
    if(child.exitCode===null)child.kill();
  }
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
