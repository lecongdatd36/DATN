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
const config=await(await fetch(base+'/__reservation_test__/config')).json();
const create=async mode=>{
await nav('/reservations/online/');
await assert("!document.querySelector('[name^=qty_]')&&Boolean(document.querySelector('.or-booking-photo'))",'Booking must have a photo and separate dish selection');
await js(`(()=>{const form=document.querySelector('#id_full_name').form;form.full_name.value='Khách thử trình duyệt ${mode}';form.phone.value='0912345688';form.starts_at.value=${JSON.stringify(config.arrival)};form.party_size.value='4';form.duration_minutes.value='120';form.requestSubmit(form.querySelector('button[data-details-submit]'));})()`);
await wait(()=>js("document.readyState==='complete'&&Boolean(document.querySelector('[data-preorder-question]'))"));
await js(`document.querySelector('[name=mode]').value=${JSON.stringify(mode)}`);await click('button[value=yes]');
await wait(()=>js("document.readyState==='complete'&&location.pathname.endsWith('/chon-mon/')"));
await assert("!document.querySelector('[name=full_name]')&&Boolean(document.querySelector('[data-preorder-cart]'))",'Menu must have its own cart UI');
await assert("document.querySelector('[data-preorder-cart]').dataset.cartReady==='true'",'Collected cart script must load and initialize');
await js("Promise.all([...document.querySelectorAll('.or-product-photo')].map(async img=>{img.loading='eager';await img.decode()}))");
await assert("[...document.querySelectorAll('.or-product-photo')].every(img=>img.complete&&img.naturalWidth>0)",'Dish images must load');
await click(`[data-dish-id="${config.dish}"] button[data-quantity-delta="1"]`);await click(`[data-dish-id="${config.dish}"] button[data-quantity-delta="1"]`);
await assert("document.querySelector('[data-cart-count]').textContent==='2'&&document.querySelector('[data-cart-total]').textContent.includes('400.000')",'Cart must calculate two dishes');
await js(`document.querySelector('[name="note_${config.dish}"]').value='Ít cay, không hành'`);
if(mode==='TABLE'){
await metrics(1440,1050);await capture('guest-menu-cart-desktop');await metrics(390,844);await capture('guest-menu-mobile');
await click(`[data-cart-item="${config.dish}"] button[data-quantity-delta="1"]`);
await assert("document.querySelector('[data-cart-count]').textContent==='3'",'Cart plus must work with a real pointer on mobile');
await click(`[data-cart-item="${config.dish}"] button[data-quantity-delta="-1"]`);
await assert("document.querySelector('[data-cart-count]').textContent==='2'",'Cart minus must work with a real pointer on mobile');
await assert('document.documentElement.scrollWidth<=innerWidth+1','Menu overflows mobile');
await js("document.querySelector('.or-catalog').scrollIntoView({block:'start'})");await capture('guest-products-mobile');
await assert("[...document.querySelectorAll('.or-quantity input')].every(input=>input.getBoundingClientRect().width<=40)",'Quantity controls must fit dish cards');
await js("document.querySelector('#reservation-cart').scrollIntoView({block:'start'})");await capture('guest-cart-mobile');
await js("document.querySelector('[data-dish-search]').value='khongtimthay';document.querySelector('[data-dish-search]').dispatchEvent(new Event('input',{bubbles:true}))");
await assert("!document.querySelector('[data-no-results]').hidden&&!document.querySelector('[data-cart-item]').hidden",'Filtering must keep the cart');
await js("document.querySelector('[data-dish-search]').value='bun';document.querySelector('[data-dish-search]').dispatchEvent(new Event('input',{bubbles:true}))");
await assert("!document.querySelector('[data-dish-id]').hidden",'Search should match Vietnamese without accents');
await click('[data-remove]');await assert("document.querySelector('[data-cart-count]').textContent==='0'&&!document.querySelector('[data-cart-empty]').hidden",'Remove should empty cart');
await click(`[data-dish-id="${config.dish}"] button[data-quantity-delta="1"]`);await click(`[data-dish-id="${config.dish}"] button[data-quantity-delta="1"]`);
await js(`document.querySelector('[name="note_${config.dish}"]').value='Ít cay, không hành'`);
await js("document.querySelector('button[value=back]').click()");await wait(()=>js("document.readyState==='complete'&&location.pathname==='/reservations/online/'"));
await assert("document.querySelector('[name=full_name]').value==='Khách thử trình duyệt TABLE'",'Back should preserve details');
await js("document.querySelector('button[data-details-submit]').click()");await wait(()=>js("document.readyState==='complete'&&Boolean(document.querySelector('[data-preorder-question]'))"));await click('button[value=yes]');await wait(()=>js("document.readyState==='complete'&&location.pathname.endsWith('/chon-mon/')"));
await assert(`document.querySelector('[name="qty_${config.dish}"]').value==='2'&&document.querySelector('[name="note_${config.dish}"]').value==='Ít cay, không hành'`,'Back should preserve cart and note');
}
await js("document.querySelector('button[value=review]').click()");await wait(()=>js("document.readyState==='complete'&&location.pathname.endsWith('/xac-nhan/')"));
await assert("!document.querySelector('[name=agree]').checked&&document.body.textContent.includes('Ít cay, không hành')",'Review must show notes and require explicit consent');
if(mode==='TABLE'){await metrics(1440,1050);await capture('guest-review-desktop');await metrics(390,844);await assert('document.documentElement.scrollWidth<=innerWidth+1','Review overflows mobile');await capture('guest-review-mobile');}
await js("document.querySelector('[name=agree]').checked=true;document.querySelector('[name=agree]').form.requestSubmit()");
await wait(()=>js("document.readyState==='complete'&&Boolean(document.querySelector('[data-reservation-watch]'))"));
return await js('location.pathname');
};
const pay=async()=>{await js("document.querySelector('button[value=pay]').form.querySelector('[name=agree]').checked=true;document.querySelector('button[value=pay]').click()");await wait(()=>js("Boolean(document.querySelector('#confirm-fixture'))"));await js("document.querySelector('#confirm-fixture').click()");await wait(()=>js("document.readyState==='complete'&&document.body.textContent.includes('Đã nhận cọc và xác nhận')"));};
await metrics(1440,1050);await nav('/reservations/online/');await capture('guest-booking-desktop');await metrics(390,844);await capture('guest-booking-mobile');await assert('document.documentElement.scrollWidth<=innerWidth+1','Booking form overflows mobile');
await assert("Boolean(document.querySelector('[name=full_name]'))&&!document.querySelector('[data-booking-choice]')&&!document.querySelector('[name=mode]')",'Entry must directly show the single booking form');
await assert("getComputedStyle(document.querySelector('.or-booking-content h2')).fontFamily.includes('Segoe UI')",'Booking headings must use a font with Vietnamese coverage');
await metrics(1440,1050);await capture('guest-table-details-desktop');await metrics(390,844);await capture('guest-table-details-mobile');
await js(`(()=>{const form=document.querySelector('#id_full_name').form;form.full_name.value='Khách chỉ đặt bàn';form.phone.value='0912345688';form.starts_at.value=${JSON.stringify(config.arrival)};form.party_size.value='4';form.duration_minutes.value='120';form.requestSubmit(form.querySelector('[data-details-submit]'));})()`);
await wait(()=>js("document.readyState==='complete'&&Boolean(document.querySelector('[data-preorder-question]'))"));
await metrics(1440,1050);await capture('guest-preorder-question-desktop');await metrics(390,844);await capture('guest-preorder-question-mobile');
await assert("document.body.textContent.includes('Bạn có muốn đặt món trước không?')",'Ask about preorder only after entering booking details');
await click('button[value=no]');
await wait(()=>js("document.readyState==='complete'&&location.pathname.endsWith('/xac-nhan/')"));
await assert("!document.body.textContent.includes('Giỏ món')&&!document.body.textContent.includes('Cách chuẩn bị')&&!document.querySelector('a[href$=\"/chon-mon/\"]')",'Table-only review must not contain a cart or menu step');
await assert('document.documentElement.scrollWidth<=innerWidth+1','Table-only review overflows mobile');
await capture('guest-table-review-mobile');await metrics(1440,1050);await capture('guest-table-review-desktop');
const a=await create('TABLE');await assert("document.body.textContent.includes('Chờ thanh toán cọc')",'A must wait for deposit');await pay();await capture('guest-a-paid-mobile');
const aCode=await js("document.querySelector('.or-summary strong').textContent.trim()");
await nav('/reservations/online/tra-cuu/');
await js(`(()=>{const form=document.querySelector('[name=reservation_code]').form;form.reservation_code.value=${JSON.stringify(aCode)};form.phone.value='0912345688';form.requestSubmit();})()`);
await wait(()=>js("document.readyState==='complete'&&Boolean(document.querySelector('.or-summary'))"));
await assert(`document.body.textContent.includes('100.000')&&Boolean(document.querySelector('a[href="${a}"]'))&&document.body.textContent.includes('Món đã được ghi nhận, chờ khách đến.')`,'Owner lookup must show deposit, preparation state and private detail link');
await assert('document.documentElement.scrollWidth<=innerWidth+1','Detailed lookup overflows mobile');await capture('guest-lookup-mobile');
await metrics(1440,1050);await capture('guest-lookup-desktop');await metrics(390,844);
const b=await create('READY');await assert("document.body.textContent.includes('Chờ nhà hàng xem xét')&&!document.querySelector('button[value=pay]')",'B must be reviewed before payment');
await metrics(1440,1050);await page.call('Page.navigate',{url:base+'/__reservation_test__/login'});await wait(()=>js("document.readyState==='complete'&&location.pathname.endsWith('/quan-ly/')"));
const staffB=await js("[...document.querySelectorAll('tbody tr')].find(row=>row.textContent.includes('Khách thử trình duyệt READY')).querySelector('a').getAttribute('href')");await nav(staffB);
await js(`(()=>{const button=document.querySelector('button[value=offer]'),form=button.form;form.prep_starts_at.value=${JSON.stringify(config.prep)};form.ready_by.value=${JSON.stringify(config.arrival)};form.note.value='Đã thống nhất món và giờ phục vụ';form.requestSubmit(button);})()`);
await wait(()=>js("document.readyState==='complete'&&document.body.textContent.includes('Chờ khách đồng ý bản chốt')"));await capture('staff-offer-desktop');
await page.call('Network.enable');await page.call('Network.clearBrowserCookies');await nav(b);
await js("document.querySelector('button[value=accept]').form.querySelector('[name=agree]').checked=true;document.querySelector('button[value=accept]').click()");await wait(()=>js("Boolean(document.querySelector('button[value=pay]'))"));await pay();await capture('guest-b-paid-desktop');
await fetch(base+'/__reservation_test__/clock?at=prep',{method:'POST'});
await page.call('Page.navigate',{url:base+'/__reservation_test__/login'});await wait(()=>js("document.readyState==='complete'&&location.pathname.endsWith('/quan-ly/')"));await nav('/reservations/online/bep/');
await assert("document.querySelectorAll('[data-preorder-mode=TABLE]').length===1&&!document.querySelector('[data-preorder-mode=TABLE] form')&&Boolean(document.querySelector('[data-preorder-mode=READY] form'))",'Paid table preorders must be visible while only scheduled advance preparation has kitchen controls');
await capture('kitchen-preorders-desktop');await metrics(390,844);await assert('document.documentElement.scrollWidth<=innerWidth+1','Preorder kitchen overflows mobile');await capture('kitchen-preorders-mobile');await metrics(1440,1050);
for(const state of ['PENDING','COOKING','READY']){await js(`document.querySelector('button[value=${state}]').click()`);await wait(()=>js(`document.readyState==='complete'&&!document.querySelector('button[value=${state}]')`));}
await capture('kitchen-ready-desktop');
await fetch(base+'/__reservation_test__/clock?at=arrival',{method:'POST'});await nav(staffB);await js("document.querySelector('button[value=receive]').click()");await wait(()=>js("document.readyState==='complete'&&location.pathname==='/sales/'"));await capture('received-pos-desktop');
await assert("document.body.textContent.includes('Khấu trừ')||document.body.textContent.includes('Cọc đã nhận')",'POS must show prepaid deposit');
const report='ONLINE RESERVATION BROWSER CHECKS PASSED\nReal guest A/B creation, detailed owner lookup, paid preorder visibility, staff quote, guest acceptance, signed IPN through LOCAL bank fixture, timed kitchen preparation, physical check-in and POS deposit preview. No external banking request.\n';await writeFile(path.join(output,'checks.txt'),report);process.stdout.write(report);
}finally{if(page)page.socket.close();if(browser){try{await Promise.race([browser.call('Browser.close'),sleep(2000)]);}catch{}browser.socket.close();}if(child.exitCode===null)child.kill();}
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
