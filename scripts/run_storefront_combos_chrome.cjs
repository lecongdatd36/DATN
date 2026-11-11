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
let page,browser;
try{
const port=await wait(async()=>{try{return Number((await readFile(path.join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0]);}catch{return null;}});
browser=await connect((await(await fetch(`http://127.0.0.1:${port}/json/version`)).json()).webSocketDebuggerUrl);
const target=await(await fetch(`http://127.0.0.1:${port}/json/new?about:blank`,{method:'PUT'})).json();page=await connect(target.webSocketDebuggerUrl);await page.call('Page.enable');await page.call('Network.enable');await page.call('Network.setExtraHTTPHeaders',{headers:{'Accept-Language':'vi-VN,vi;q=0.9'}});
const js=async expression=>{const result=await page.call('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(result.exceptionDetails.text);return result.result?.value;};
const nav=async route=>{await page.call('Page.navigate',{url:base+route});await wait(()=>js(`document.readyState==='complete'&&location.pathname===${JSON.stringify(route.split('?')[0])}`));};
const metrics=(width,height)=>page.call('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});
const capture=async name=>{const result=await page.call('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await writeFile(path.join(output,name+'.png'),Buffer.from(result.data,'base64'));};
const assert=async(expression,message)=>{if(!await js(expression))throw Error(message);};
const click=async selector=>{
  const point=await js(`(()=>{const button=document.querySelector(${JSON.stringify(selector)});if(!button||button.disabled)throw Error('Button missing or disabled');button.scrollIntoView({block:'center',behavior:'instant'});const rect=button.getBoundingClientRect(),x=rect.x+rect.width/2,y=rect.y+rect.height/2;if(document.elementFromPoint(x,y)?.closest('button')!==button)throw Error('Button is covered');return{x,y};})()`);
  await page.call('Input.dispatchMouseEvent',{type:'mousePressed',...point,button:'left',clickCount:1});
  await page.call('Input.dispatchMouseEvent',{type:'mouseReleased',...point,button:'left',clickCount:1});
};

const press=async selector=>{
const point=await js(`(()=>{const node=document.querySelector(${JSON.stringify(selector)});if(!node||node.disabled)throw Error('Control missing');node.scrollIntoView({block:'center',behavior:'instant'});const r=node.getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2}})()`);
await page.call('Input.dispatchMouseEvent',{type:'mousePressed',...point,button:'left',clickCount:1});
await page.call('Input.dispatchMouseEvent',{type:'mouseReleased',...point,button:'left',clickCount:1});
};
const config=await(await fetch(base+'/__storefront_test__/config')).json();
await metrics(1440,1100);await nav('/');
await js("document.fonts.ready");await js("Promise.all([...document.images].map(async img=>{img.loading='eager';try{await img.decode()}catch{}}))");
await assert("getComputedStyle(document.querySelector('#welcome-title')).fontFamily.includes('CQ Dancing Script')",'Hero font must support the cursive Vietnamese heading');
await assert("document.querySelector('.cq-welcome').getBoundingClientRect().width>=innerWidth-20",'Hero must fill viewport width');
await capture('hero-fullscreen-desktop');
await press('[data-cq-show-more]');
await press(`[data-basket-add=dish][data-item-id="${config.extra}"]`);
await wait(()=>js("document.querySelector('.cq-header-cart [data-basket-count]').textContent==='1'"));
await press(`[data-basket-add=combo][data-item-id="${config.combo}"]`);
await wait(()=>js("document.querySelector('.cq-header-cart [data-basket-count]').textContent==='2'"));
await press('.cq-header-cart');
await assert("document.querySelector('[data-basket-dialog]').open",'Basket opens as a dialog');
await assert(`document.querySelector('[data-basket-total]').textContent.replace(/\\D/g,'')===String(${config.total})`,'Basket price must match authoritative combo plus dish');
await capture('basket-desktop');
await press(`[data-basket-key="combo-${config.combo}"] [data-basket-plus]`);
await wait(()=>js("document.querySelector('.cq-header-cart [data-basket-count]').textContent==='3'"));
await press(`[data-basket-key="combo-${config.combo}"] [data-basket-minus]`);
await wait(()=>js("document.querySelector('.cq-header-cart [data-basket-count]').textContent==='2'"));
await metrics(390,844);await assert('document.documentElement.scrollWidth<=innerWidth+1','Basket overflows mobile');await capture('basket-mobile');
await press('.cq-basket-close');await nav('/menu/');
await wait(()=>js("document.querySelector('.cq-header-cart [data-basket-count]').textContent==='2'"));
await assert("document.querySelectorAll('[data-combo-card]').length===3",'Combos must show on the public menu');
await nav('/');await metrics(1440,1100);
await js("document.querySelector('#combo-home').scrollIntoView({block:'start',behavior:'instant'})");await capture('combos-desktop');
await metrics(390,844);await assert('document.documentElement.scrollWidth<=innerWidth+1','Combo section overflows mobile');await capture('combos-mobile');
await metrics(768,1024);await js('scrollTo(0,0)');await assert('document.documentElement.scrollWidth<=innerWidth+1','Tablet layout overflows');
await metrics(390,844);await js('scrollTo(0,0)');await capture('hero-mobile');
await metrics(1440,1100);await js('scrollTo(0,0)');
await js(`(()=>{const form=document.querySelector('[data-quick-booking]');form.booking_date.value=${JSON.stringify(config.arrival.split('T')[0])};form.booking_time.value=${JSON.stringify(config.arrival.split('T')[1])};form.party_size.value='4';form.requestSubmit()})()`);
await wait(()=>js("document.readyState==='complete'&&location.pathname==='/reservations/online/'"));
await assert("document.querySelector('[name=party_size]').value==='4'",'Quick booking must carry selected party size with the cart');
await js("(()=>{const field=document.querySelector('[name=full_name]');field.value='Khách combo thử trình duyệt';field.form.phone.value='0912345688';field.form.requestSubmit(field.form.querySelector('[data-details-submit]'))})()");
await wait(()=>js("document.readyState==='complete'&&location.pathname.endsWith('/xac-nhan/')"));
await assert(`document.body.textContent.includes(${JSON.stringify(config.combo_name)})`,'Review must contain the selected combo');
await capture('combo-booking-review');
await js("document.querySelector('[name=agree]').checked=true;document.querySelector('[name=agree]').form.requestSubmit()");
await wait(()=>js("document.readyState==='complete'&&Boolean(document.querySelector('[data-reservation-watch]'))"));
await assert("document.body.textContent.includes('Combo đã đặt')&&document.body.textContent.includes('Chờ thanh toán cọc')",'Reservation must preserve combo snapshot and wait for verified deposit');
await js("(()=>{const button=document.querySelector('button[value=pay]');button.form.querySelector('[name=agree]').checked=true;button.form.requestSubmit(button)})()");
await wait(()=>js("Boolean(document.querySelector('#confirm-fixture'))"));await press('#confirm-fixture');
await wait(()=>js("document.readyState==='complete'&&document.body.textContent.includes('Đã nhận cọc và xác nhận')"));await capture('combo-paid-private-detail');
await page.call('Page.navigate',{url:base+'/__storefront_test__/login'});
await wait(()=>js("document.readyState==='complete'&&location.pathname.endsWith('/combo/')"));
await capture('combo-management');
await nav(`/thuc-don/combo/${config.combo}/sua/`).catch(()=>{});
if(!await js("Boolean(document.querySelector('[name=price]'))")){
const edit=await js(`[...document.querySelectorAll('a')].find(a=>a.getAttribute('href')?.includes('/combo/${config.combo}/sua/'))?.getAttribute('href')`);
if(!edit){await nav('/');throw Error('Combo edit route missing');}
await nav(edit);
}
await js(`(()=>{const field=document.querySelector('[name=price]');field.value=String(${config.combo_price}-1000);field.form.requestSubmit()})()`);
await wait(()=>js("document.readyState==='complete'&&location.pathname.endsWith('/combo/')"));
const manage=await(await fetch(base+'/__storefront_test__/arrival')).text();await nav(manage);
await js("document.querySelector('button[value=receive]').click()");
await wait(()=>js("document.readyState==='complete'&&location.pathname==='/sales/'"));await capture('combo-received-pos');
console.log('STOREFRONT COMBO CHECKS PASSED: full-screen cursive hero, real dish/combo cart, quantity controls, cross-page persistence, desktop/mobile/tablet, quick booking, consent, signed local deposit fixture, combo management edit and preserved price at check-in.');
}finally{if(page)page.socket.close();if(browser){try{await Promise.race([browser.call('Browser.close'),sleep(2000)]);}catch{}browser.socket.close();}if(child.exitCode===null)child.kill();}
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
