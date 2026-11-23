const {spawn}=require('node:child_process');
const {readFile,writeFile}=require('node:fs/promises');
const path=require('node:path');
const [base,profile,out]=process.argv.slice(2);
if(new URL(base).hostname!=='127.0.0.1')throw Error('Local fixture server only');
const delay=ms=>new Promise(r=>setTimeout(r,ms));
async function until(fn){const end=Date.now()+15000;while(Date.now()<end){const v=await fn();if(v)return v;await delay(80);}throw Error('Timed out waiting for application page');}
async function connect(url){
 const socket=new WebSocket(url),pending=new Map();let id=0;
 await new Promise((ok,no)=>{socket.addEventListener('open',ok,{once:true});socket.addEventListener('error',no,{once:true});});
 socket.addEventListener('message',e=>{const m=JSON.parse(e.data),p=pending.get(m.id);if(!p)return;pending.delete(m.id);m.error?p.reject(Error(m.error.message)):p.resolve(m.result);});
 return {socket,call(method,params={}){return new Promise((resolve,reject)=>{const n=++id;pending.set(n,{resolve,reject});socket.send(JSON.stringify({id:n,method,params}));});}};
}
(async()=>{
 const config=await(await fetch(base+'/__section33__/config')).json();
 const child=spawn('C:/Program Files/Google/Chrome/Application/chrome.exe',['--headless=new','--no-sandbox','--disable-gpu','--no-first-run','--disable-background-networking','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{windowsHide:true,stdio:'ignore'});
 let browser,page;
 try{
  const port=await until(async()=>{try{return Number((await readFile(path.join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0]);}catch{return null;}});
  browser=await connect((await(await fetch(`http://127.0.0.1:${port}/json/version`)).json()).webSocketDebuggerUrl);
  page=await connect((await(await fetch(`http://127.0.0.1:${port}/json/new?about:blank`,{method:'PUT'})).json()).webSocketDebuggerUrl);
  await page.call('Page.enable');await page.call('Network.enable');
  await page.call('Emulation.setDeviceMetricsOverride',{width:430,height:920,deviceScaleFactor:2,mobile:true});
  const js=async expression=>{const r=await page.call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value;};
  async function role(name){await page.call('Network.clearBrowserCookies');if(name)await page.call('Network.setCookie',{name:config.cookie,value:config.sessions[name],url:base,path:'/'});}
  async function nav(route){const expected=[route.split('?')[0],config.routes['sales:mobile']];await page.call('Page.navigate',{url:base+route});await until(()=>js(`document.readyState==='complete'&&${JSON.stringify(expected)}.includes(location.pathname)`));await js('document.fonts.ready.then(()=>true)');await delay(200);}
  async function shot(name,selector=null){if(selector)await js(`(()=>{const n=document.querySelector(${JSON.stringify(selector)});if(!n)throw Error('Screenshot target missing');n.scrollIntoView({block:'start'});scrollBy(0,-90);})()`);else await js('scrollTo(0,0)');await delay(100);const r=await page.call('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await writeFile(path.join(out,name+'.png'),Buffer.from(r.data,'base64'));console.log(name);}
  await role(null);await nav(config.routes['accounts:login']);
  if(await js("[...document.querySelectorAll('input[type=password]')].some(x=>x.value)"))throw Error('Password field must be empty');
  await shot('login');
  await role('MANAGER');await nav(config.routes['accounts:workspace']);await shot('manager');
  await role('KITCHEN');await nav(config.routes['kitchen:workspace']);await shot('kitchen');
  await role('ROOT');await nav(config.routes.employee_edit);
  await js("(()=>{const n=document.querySelector('[name=full_name]');n.value='Nhân viên phục vụ minh họa';n.form.requestSubmit();})()");
  await until(()=>js(`document.readyState==='complete'&&location.pathname===${JSON.stringify(config.routes['employees:employee_list'])}`));
  if(!await js("document.body.innerText.includes('Đã cập nhật nhân viên')"))throw Error('Missing actual employee-update success message');
  await shot('employee-updated');
  await nav(config.routes['seating:table_list']);await shot('tables');
  await nav(config.routes.booking_detail);if(!await js("document.body.innerText.includes('Đã xác nhận')"))throw Error('Booking must be confirmed');await shot('booking-confirmed');
  await nav(config.routes['menu:dish_list']);await shot('menu','table');
  await nav(config.routes.order_detail);await shot('order');
  await role('INVENTORY');await nav(config.routes['inventory:workspace']);await shot('inventory','table');
  await nav(config.routes.receipt_detail);if(!await js("document.body.innerText.includes('Đã nhận')"))throw Error('Receipt must be received');await shot('receipt-received');
  await role('MANAGER');await nav(config.routes.invoice_order);await shot('invoice-paid');
  await nav(config.routes['reports:dashboard']);await shot('reports','.report-filter');
  console.log('Twelve screenshots captured from real application pages.');
 }finally{
  if(browser){try{await browser.call('Browser.close');}catch{}browser.socket.close();}
  if(page)page.socket.close();child.kill();
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
