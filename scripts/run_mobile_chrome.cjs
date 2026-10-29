// Isolated headless Chrome for the disposable local integration-test server.
const {spawn} = require('node:child_process');
const {readFile,writeFile} = require('node:fs/promises');
const path = require('node:path');
const [baseUrl,profile,output] = process.argv.slice(2);
if (new URL(baseUrl).hostname !== '127.0.0.1') throw Error('Only the local test server is supported');
const sleep = ms => new Promise(resolve=>setTimeout(resolve,ms));
async function connect(url) {
  const socket = new WebSocket(url),pending=new Map();let sequence=0;
  await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
  socket.addEventListener('message',event=>{
    const message=JSON.parse(event.data),request=pending.get(message.id);
    if(!request)return;pending.delete(message.id);
    if(message.error)request.reject(Error(message.error.message));else request.resolve(message.result);
  });
  return {socket,call(method,params={}){return new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,{resolve,reject});socket.send(JSON.stringify({id,method,params}));});}};
}
async function waitUntil(callback,timeout=45000) {
  const end=Date.now()+timeout;
  while(Date.now()<end){const value=await callback();if(value)return value;await sleep(60);}
  throw Error('Browser check timed out');
}
(async()=>{
  const child=spawn('C:/Program Files/Google/Chrome/Application/chrome.exe',[
    '--headless=new','--no-sandbox','--disable-gpu','--disable-software-rasterizer','--no-first-run','--hide-scrollbars',
    '--disable-background-networking','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'
  ],{windowsHide:true,stdio:'ignore'});
  let browser,page;
  try{
    const port=await waitUntil(async()=>{try{return Number((await readFile(path.join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0]);}catch{return null;}},10000);
    const info=await (await fetch(`http://127.0.0.1:${port}/json/version`)).json();browser=await connect(info.webSocketDebuggerUrl);
    const target=await (await fetch(`http://127.0.0.1:${port}/json/new?${encodeURIComponent(baseUrl+'/__mobile_test__/')}`,{method:'PUT'})).json();
    page=await connect(target.webSocketDebuggerUrl);await page.call('Page.enable');
    const evaluate=async expression=>(await page.call('Runtime.evaluate',{expression,returnByValue:true})).result?.value;
    const report=await waitUntil(async()=>{const report=await evaluate('document.querySelector("#result")?.textContent || ""');return report?.includes('LIVE CHECKS PASSED')||report?.includes('FAIL ')?report:null;});
    await writeFile(path.join(output,'live-checks.txt'),report,'utf8');
    if(!report.includes('LIVE CHECKS PASSED'))throw Error(report);
    await page.call('Emulation.setDeviceMetricsOverride',{width:500,height:932,deviceScaleFactor:1,mobile:false});
    for(const name of ['tables','payments','open','menu','order','checkout','receipt']){
      await page.call('Page.navigate',{url:baseUrl+'/__mobile_test__/capture/'+name});
      await waitUntil(()=>evaluate(`document.querySelector('iframe')?.contentDocument?.readyState==='complete' && Boolean(document.querySelector('iframe')?.contentDocument?.querySelector('.m-header'))`),10000);
      const screenshot=await page.call('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
      await writeFile(path.join(output,name+'-live.png'),Buffer.from(screenshot.data,'base64'));
      if(name==='open'){
        await evaluate(`(()=>{const doc=document.querySelector('iframe').contentDocument,input=doc.querySelector('[data-customer-phone]');input.value='0901234567';input.dispatchEvent(new doc.defaultView.Event('input',{bubbles:true}));doc.querySelector('[data-customer-find]').click();})()`);
        await waitUntil(()=>evaluate(`Boolean(document.querySelector('iframe')?.contentDocument?.querySelector('[data-open-form]')?.dataset.verifiedPhone)`),10000);
        await evaluate(`document.querySelector('iframe').contentDocument.querySelector('[data-customer-phone]').focus()`);
        const customerScreenshot=await page.call('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
        await writeFile(path.join(output,'open-customer-live.png'),Buffer.from(customerScreenshot.data,'base64'));
      }
    }
    process.stdout.write(report+'\n');
  }finally{
    if(page)page.socket.close();
    if(browser){try{await Promise.race([browser.call('Browser.close'),sleep(2000)]);}catch{}browser.socket.close();}
    if(child.exitCode===null)child.kill();
  }
})().catch(error=>{console.error(error.message);process.exitCode=1;});
