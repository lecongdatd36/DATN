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
const config=await(await fetch(base+'/__payment_test__/config')).json();
await metrics(1440,1000);await page.call('Page.navigate',{url:base+'/__payment_test__/login'});
await wait(()=>js("document.readyState==='complete'&&Boolean(document.querySelector('[data-zalopay-result]'))"));
await assert("Boolean(document.querySelector('.admin-sidebar'))&&!document.querySelector('.customer-header')&&!document.querySelector('[data-basket-dialog]')",'POS payment must keep the internal management layout');
await assert("document.querySelector('h1').textContent==='Kết quả thanh toán'&&!document.body.textContent.includes('thanh toán thử nghiệm')",'Result heading must use neutral demo labels');
await capture('pending-pos-desktop');
await metrics(390,844);await assert('document.documentElement.scrollWidth<=innerWidth+1','Payment result overflows mobile');await capture('pending-pos-mobile');
await metrics(1440,1000);await fetch(base+'/__payment_test__/confirm',{method:'POST'});
await wait(()=>js("document.readyState==='complete'&&location.pathname==='/sales/'&&Boolean(document.querySelector('[role=status]'))"));
await assert("document.body.textContent.includes('Đã thanh toán hóa đơn')&&!document.querySelector('.customer-header')",'Verified payment must return automatically to POS with the paid receipt');
await capture('paid-pos-return');
await page.call('Network.setUserAgentOverride',{userAgent:'Mozilla/5.0 (iPhone; Mobile) AppleWebKit/537.36 Safari/537.36'});
await metrics(390,844);await page.call('Page.navigate',{url:base+config.result});
await wait(()=>js("document.readyState==='complete'&&location.pathname==='/sales/mobile/'&&new URLSearchParams(location.search).get('page')==='receipt'"));
await capture('paid-mobile-receipt');
await assert("!document.querySelector('[data-zalopay-result]')&&!document.querySelector('.customer-header')",'Mobile payment must return to its receipt, not customer checkout');
console.log('PAYMENT RETURN BROWSER CHECKS PASSED: internal pending page, neutral labels, responsive layout, signed callback -> automatic POS return, paid invoice banner and mobile receipt.');
}finally{if(page)page.socket.close();if(browser){try{await Promise.race([browser.call('Browser.close'),sleep(2000)]);}catch{}browser.socket.close();}if(child.exitCode===null)child.kill();}
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
