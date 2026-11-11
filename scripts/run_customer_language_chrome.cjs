const {spawn}=require('node:child_process');
const {readFile,writeFile}=require('node:fs/promises');
const path=require('node:path');
const [base,profile,output]=process.argv.slice(2);
if(new URL(base).hostname!=='127.0.0.1')throw Error('Local test server only');
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function wait(fn,timeout=20000){const end=Date.now()+timeout;while(Date.now()<end){const value=await fn();if(value)return value;await sleep(100);}throw Error('Browser check timed out');}
async function connect(url){const socket=new WebSocket(url),pending=new Map();let id=0;await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});socket.addEventListener('message',event=>{const data=JSON.parse(event.data),task=pending.get(data.id);if(!task)return;pending.delete(data.id);data.error?task.reject(Error(data.error.message)):task.resolve(data.result);});return{socket,call(method,params={}){return new Promise((resolve,reject)=>{const key=++id;pending.set(key,{resolve,reject});socket.send(JSON.stringify({id:key,method,params}));});}};}
(async()=>{
const child=spawn('C:/Program Files/Google/Chrome/Application/chrome.exe',['--headless=new','--no-sandbox','--disable-gpu','--no-first-run','--disable-background-networking','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{windowsHide:true,stdio:'ignore'});
let page,browser,js,capture;
try{
const port=await wait(async()=>{try{return Number((await readFile(path.join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0]);}catch{return null;}});
browser=await connect((await(await fetch(`http://127.0.0.1:${port}/json/version`)).json()).webSocketDebuggerUrl);
const target=await(await fetch(`http://127.0.0.1:${port}/json/new?about:blank`,{method:'PUT'})).json();page=await connect(target.webSocketDebuggerUrl);await page.call('Page.enable');await page.call('Network.enable');await page.call('Network.setExtraHTTPHeaders',{headers:{'Accept-Language':'vi-VN,vi;q=0.9'}});
js=async expression=>{const result=await page.call('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result?.value;};
const nav=async route=>{await page.call('Page.navigate',{url:base+route});await wait(()=>js(`document.readyState==='complete'&&location.pathname===${JSON.stringify(route.split('?')[0])}`));};
const metrics=(width,height)=>page.call('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});
capture=async name=>{const result=await page.call('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await writeFile(path.join(output,name+'.png'),Buffer.from(result.data,'base64'));};
const assert=async(expression,message)=>{if(!await js(expression))throw Error(message);};
const click=async selector=>{
  const point=await js(`(()=>{const button=document.querySelector(${JSON.stringify(selector)});if(!button||button.disabled)throw Error('Button missing or disabled');button.scrollIntoView({block:'center',behavior:'instant'});const rect=button.getBoundingClientRect(),x=rect.x+rect.width/2,y=rect.y+rect.height/2;if(document.elementFromPoint(x,y)?.closest('button')!==button)throw Error('Button is covered');return{x,y};})()`);
  await page.call('Input.dispatchMouseEvent',{type:'mousePressed',...point,button:'left',clickCount:1});
  await page.call('Input.dispatchMouseEvent',{type:'mouseReleased',...point,button:'left',clickCount:1});
};


const config=await(await fetch(base+'/__storefront_test__/config')).json();
const press=async selector=>{
 const point=await js(`(()=>{const n=document.querySelector(${JSON.stringify(selector)});if(!n||n.disabled)throw Error('Control missing');n.scrollIntoView({block:'center',behavior:'instant'});const r=n.getBoundingClientRect();if(!r.width||!r.height)throw Error('Control hidden');const x=r.x+r.width/2,y=r.y+r.height/2;if(document.elementFromPoint(x,y)?.closest('button,a')!==n)throw Error('Control covered by '+document.elementFromPoint(x,y)?.className);return{x,y}})()`);
 await page.call('Input.dispatchMouseEvent',{type:'mousePressed',...point,button:'left',clickCount:1});
 await page.call('Input.dispatchMouseEvent',{type:'mouseReleased',...point,button:'left',clickCount:1});
};
const switchLanguage=async language=>{
 await js('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))');
 await press(`.cq-language-switch button[value="${language}"]`);
 await wait(()=>js(`document.readyState==='complete'&&document.documentElement.lang===${JSON.stringify(language)}`));
 await js('document.fonts.ready');
};
await metrics(1440,1100);await nav('/menu/?q='+encodeURIComponent('Trà')+'&category='+config.extra_category);
await assert("document.documentElement.lang==='vi'&&Boolean(document.querySelector('.cq-welcome'))",'Menu must have the shared full-width banner in Vietnamese');
await js('document.fonts.ready');await capture('menu-banner-vi-desktop');
const savedQuery=await js('location.search');
await switchLanguage('en');
await assert(`location.search===${JSON.stringify(savedQuery)}`,'Language switching must preserve menu search/category');
await assert("document.body.textContent.includes('Pick your favourites.')&&document.querySelector('.cq-welcome').getBoundingClientRect().width>=innerWidth-20",'Menu banner must match the homepage in English');
await assert(`document.body.textContent.includes(${JSON.stringify(config.extra_name_en)})&&document.body.textContent.includes(${JSON.stringify(config.combo_name_en)})`,'English dish and combo names must render');
await capture('menu-banner-en-desktop');
await press(`[data-basket-add=dish][data-item-id="${config.extra}"]`);
await wait(()=>js("document.querySelector('.cq-header-cart [data-basket-count]').textContent==='1'"));
await press(`[data-basket-add=combo][data-item-id="${config.combo}"]`);
await wait(()=>js("document.querySelector('.cq-header-cart [data-basket-count]').textContent==='2'"));
await press('.cq-header-cart');
await assert("document.querySelector('#basket-heading').textContent==='Your food basket'&&document.querySelector('[data-basket-checkout]').textContent.includes('Continue to booking')",'English JavaScript basket labels must load');
await assert(`document.querySelector('[data-basket-total]').textContent.replace(/\\D/g,'')===String(${config.total})`,'Language must not change basket prices');
await capture('basket-en-desktop');await metrics(390,844);await capture('basket-en-mobile');await assert('document.documentElement.scrollWidth<=innerWidth+1','English basket overflows mobile');
await press('.cq-basket-close');await wait(()=>js("!document.querySelector('[data-basket-dialog]').open"));
await switchLanguage('vi');await wait(()=>js("document.querySelector('.cq-header-cart [data-basket-count]').textContent==='2'"));
await press('.cq-header-cart');await assert("document.querySelector('#basket-heading').textContent==='Giỏ món của bạn'",'Switch back must localize the existing basket');
await press('.cq-basket-close');await wait(()=>js("!document.querySelector('[data-basket-dialog]').open"));await switchLanguage('en');await wait(()=>js("document.querySelector('.cq-header-cart [data-basket-count]').textContent==='2'"));
await js('scrollTo(0,0)');await capture('menu-banner-en-mobile');
await metrics(360,844);await assert('document.documentElement.scrollWidth<=innerWidth+1','Language switcher overflows narrow mobile');
await press('[data-customer-menu-toggle]');await assert("document.querySelector('#customer-navigation').classList.contains('is-open')",'English mobile navigation must open');await press('[data-customer-menu-toggle]');
await metrics(768,1024);await assert('document.documentElement.scrollWidth<=innerWidth+1','English menu overflows tablet');
await metrics(1440,1100);
await js("(()=>{const form=document.querySelector('.cq-header-search');form.q.value='Lemon';form.requestSubmit()})()");
await wait(()=>js("document.readyState==='complete'&&document.querySelector('#dish-search')?.value==='Lemon'"));
await assert("document.querySelectorAll('.customer-menu-card').length===1&&document.querySelector('.customer-menu-card h2').textContent.includes('Lemon Tea')",'Search must match English dish names');
await nav('/');await js('document.fonts.ready');await capture('home-en-desktop');
await wait(()=>js("document.querySelector('.cq-header-cart [data-basket-count]').textContent==='2'"));
await js(`(()=>{const f=document.querySelector('[data-quick-booking]');f.booking_date.value=${JSON.stringify(config.arrival.split('T')[0])};f.booking_time.value=${JSON.stringify(config.arrival.split('T')[1])};f.party_size.value='4';f.requestSubmit()})()`);
await wait(()=>js("document.readyState==='complete'&&location.pathname==='/reservations/online/'"));
await assert("document.documentElement.lang==='en'&&document.body.textContent.includes('Full name')&&document.body.textContent.includes('Opening hours:')",'Booking labels and hours must use English');
await js("(()=>{const f=document.querySelector('[name=full_name]').form;f.full_name.value='English guest';f.phone.value='abc';f.noValidate=true;f.requestSubmit(f.querySelector('[data-details-submit]'))})()");
await wait(()=>js("document.readyState==='complete'&&document.body.textContent.includes('Enter a Vietnamese phone number')"));
await js("(()=>{const f=document.querySelector('[name=full_name]').form;f.phone.value='0912345688';f.requestSubmit(f.querySelector('[data-details-submit]'))})()");
await wait(()=>js("document.readyState==='complete'&&location.pathname.endsWith('/xac-nhan/')"));
await assert(`document.body.textContent.includes(${JSON.stringify(config.combo_name_en)})&&document.body.textContent.includes('Food subtotal')`,'English review must preserve combo selections');
await capture('booking-review-en');
await js("document.querySelector('[name=agree]').checked=true;document.querySelector('[name=agree]').form.requestSubmit()");
await wait(()=>js("document.readyState==='complete'&&Boolean(document.querySelector('[data-reservation-watch]'))"));
await assert("document.body.textContent.includes('Awaiting deposit')&&document.body.textContent.includes('Your booked combos')",'English private booking detail must render');
await js("(()=>{const b=document.querySelector('button[value=pay]');b.form.querySelector('[name=agree]').checked=true;b.form.requestSubmit(b)})()");
await wait(()=>js("Boolean(document.querySelector('#confirm-fixture'))"));await press('#confirm-fixture');
await wait(()=>js("document.readyState==='complete'&&document.body.textContent.includes('Your deposit is received')"));await capture('booking-paid-en');
await page.call('Page.navigate',{url:base+'/__storefront_test__/login'});
await wait(()=>js("document.readyState==='complete'&&location.pathname.endsWith('/combo/')"));
const manage=await(await fetch(base+'/__storefront_test__/arrival')).text();await nav(manage);
await js("document.querySelector('button[value=receive]').click()");
await wait(()=>js("document.readyState==='complete'&&location.pathname==='/sales/'"));
console.log('CUSTOMER LANGUAGE CHECKS PASSED: shared full-screen menu banner, VI/EN switch, query retention, English catalog/search, translated live basket, unchanged prices, mobile/tablet, English booking validation/review and signed fixture deposit through check-in.');
}catch(error){try{await capture('failure');console.error(await js("JSON.stringify({path:location.pathname,language:document.documentElement.lang,dialog:document.querySelector('[data-basket-dialog]')?.open})"));}catch{}throw error;}finally{if(page)page.socket.close();if(browser){try{await Promise.race([browser.call('Browser.close'),sleep(2000)]);}catch{}browser.socket.close();}if(child.exitCode===null)child.kill();}
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
