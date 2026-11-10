const {spawn}=require('node:child_process');
const {readFile,writeFile}=require('node:fs/promises');
const path=require('node:path');
const [base,profile,output]=process.argv.slice(2);
if(new URL(base).hostname!=='127.0.0.1')throw Error('Local test server only');
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function wait(fn){const end=Date.now()+20000;while(Date.now()<end){const value=await fn();if(value)return value;await sleep(100);}throw Error('Browser check timed out');}
async function connect(url){const socket=new WebSocket(url),pending=new Map();let id=0;await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});socket.addEventListener('message',event=>{const data=JSON.parse(event.data),task=pending.get(data.id);if(!task)return;pending.delete(data.id);data.error?task.reject(Error(data.error.message)):task.resolve(data.result);});return{socket,call(method,params={}){return new Promise((resolve,reject)=>{const key=++id;pending.set(key,{resolve,reject});socket.send(JSON.stringify({id:key,method,params}));});}};}
(async()=>{
const child=spawn('C:/Program Files/Google/Chrome/Application/chrome.exe',['--headless=new','--no-sandbox','--disable-gpu','--no-first-run','--disable-background-networking','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{windowsHide:true,stdio:'ignore'});
let page,browser;
try{
const port=await wait(async()=>{try{return Number((await readFile(path.join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0]);}catch{return null;}});
browser=await connect((await(await fetch(`http://127.0.0.1:${port}/json/version`)).json()).webSocketDebuggerUrl);
const target=await(await fetch(`http://127.0.0.1:${port}/json/new?about:blank`,{method:'PUT'})).json();page=await connect(target.webSocketDebuggerUrl);await page.call('Page.enable');
const js=async expression=>{const result=await page.call('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(result.exceptionDetails.text);return result.result?.value;};
const nav=async route=>{await page.call('Page.navigate',{url:base+route});await wait(()=>js("document.readyState==='complete'"));};
const metrics=(width,height)=>page.call('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});
const capture=async name=>{const result=await page.call('Page.captureScreenshot',{format:'png'});await writeFile(path.join(output,name+'.png'),Buffer.from(result.data,'base64'));};
const assert=async(expression,message)=>{if(!await js(expression))throw Error(message);};
const click=async selector=>{const point=await js(`(()=>{let el=document.querySelector(${JSON.stringify(selector)});if(!el||el.disabled)throw Error('Missing control');if(el.matches('input[type=radio]'))el=el.closest('label');el.scrollIntoView({block:'center',behavior:'instant'});const r=el.getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2};})()`);for(const type of ['mousePressed','mouseReleased'])await page.call('Input.dispatchMouseEvent',{type,...point,button:'left',clickCount:1});};
const config=await(await fetch(base+'/__zalopay_test__/config')).json();
await metrics(1440,1050);await nav('/__zalopay_test__/login');await wait(()=>js("Boolean(document.querySelector('[data-checkout-form]'))"));
await click('[name=payment_method][value=ZALOPAY]');await assert("document.querySelector('[value=ZALOPAY]').checked",'ZaloPay must be selectable');await capture('pos-zalopay-selected');
await nav('/sales/mobile/?page=checkout&order='+config.order);await wait(()=>js("Boolean(document.querySelector('[data-native-payment]'))"));await metrics(390,844);
await assert("Boolean(document.querySelector('[data-native-payment] button:not([disabled])'))",'Mobile Sandbox checkout must be enabled');
await js("document.querySelector('[data-native-payment]').scrollIntoView({block:'center',behavior:'instant'})");await capture('mobile-zalopay-option');
await click('[data-native-payment] button');await wait(()=>js("Boolean(document.querySelector('[data-zalopay-result]'))"));
await assert("document.querySelector('[data-zalopay-result]').dataset.status==='PENDING'",'Redirect must leave payment pending');
await assert('document.documentElement.scrollWidth<=innerWidth+1','Sandbox result overflows mobile');await capture('mobile-pending');
await click('[data-query-payment] button');await wait(()=>js("!document.querySelector('[data-query-payment] button').disabled"));
await assert("document.querySelector('[data-zalopay-result]').dataset.status==='PENDING'",'Unpaid query must stay pending');
const callback=await(await fetch(base+'/__zalopay_test__/confirm',{method:'POST'})).json();if(callback.return_code!==1)throw Error('Callback rejected');
await wait(()=>js("document.querySelector('[data-zalopay-result]').dataset.status==='PAID'"));await capture('mobile-paid');
await metrics(1440,1050);await capture('desktop-paid');
process.stdout.write('ZALOPAY BROWSER CHECKS PASSED: desktop selection, native mobile checkout, pending redirect, unpaid query, verified callback, paid result. No external payment.\n');
}finally{if(page)page.socket.close();if(browser){try{await Promise.race([browser.call('Browser.close'),sleep(2000)]);}catch{}browser.socket.close();}if(child.exitCode===null)child.kill();}
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
