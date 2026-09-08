import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const port=Number(process.env.HKUST_CDP_PORT||9222);
const base=process.env.HKUST_BASE||'http://127.0.0.1:4318/';
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const pages=await (await fetch(`http://127.0.0.1:${port}/json`)).json();
const page=[...pages].reverse().find(item=>item.type==='page'&&item.url.startsWith(base));
if(!page)throw new Error(`No ${base} page on CDP port ${port}`);
const socket=new WebSocket(page.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
let nextId=0;const pending=new Map();
socket.addEventListener('message',event=>{const message=JSON.parse(String(event.data));if(!message.id||!pending.has(message.id))return;const target=pending.get(message.id);pending.delete(message.id);message.error?target.reject(new Error(JSON.stringify(message.error))):target.resolve(message.result);});
const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++nextId;pending.set(id,{resolve,reject});socket.send(JSON.stringify({id,method,params}));});
const evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true,userGesture:true});if(result.exceptionDetails)throw new Error(JSON.stringify(result.exceptionDetails));return result.result.value;};
await send('Emulation.setDeviceMetricsOverride',{width:1440,height:913,deviceScaleFactor:1,mobile:false});
let chosen={ok:true,label:'本科生宿舍12座',reused:true};
if(process.env.HKUST_REUSE!=='1'){
  await evaluate(`localStorage.setItem('hkust-map-locale','zh-Hans');localStorage.setItem('hkust-map-quality','ultra');location.reload();true`);
  await sleep(12000);
  chosen=await evaluate(`(async()=>{const input=document.querySelector('input[aria-label="搜索校园实体"]');if(!input)return {ok:false,error:'search-input-missing'};const setter=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;setter.call(input,'本科生宿舍12座');input.dispatchEvent(new Event('input',{bubbles:true}));await new Promise(r=>setTimeout(r,700));const button=[...document.querySelectorAll('.entity-results>button')].find(b=>(b.querySelector('strong')?.textContent||'').includes('本科生宿舍12座'));if(!button)return {ok:false,error:'result-missing'};button.click();return {ok:true,label:button.querySelector('strong')?.textContent||''}})()`);
  if(!chosen.ok)throw new Error(JSON.stringify(chosen));
  await sleep(12000);
  for(let angle=0;angle<2;angle++){
    await send('Input.dispatchMouseEvent',{type:'mousePressed',x:720,y:500,button:'left',buttons:1,clickCount:1});
    await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:1030,y:475,button:'left',buttons:1});
    await send('Input.dispatchMouseEvent',{type:'mouseReleased',x:1030,y:475,button:'left',buttons:0,clickCount:1});
    await sleep(9000);
  }
}
const screenshot='docs/screenshots/v4/ivillage-multiangle-u73/sky-floater-debug-before.png';
const prePickState=await evaluate(`(()=>{try{return JSON.parse(document.querySelector('.atlas-world')?.dataset.sceneState||'null')}catch{return null}})()`);
const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
await fs.writeFile(path.join(root,screenshot),Buffer.from(shot.data,'base64'));
const samples=[];
const requested=process.env.HKUST_FIRST_PIXEL?.split(',').map(Number);
const pixels=requested?.length===2&&requested.every(Number.isFinite)?[requested]:[[1322,256],[1318,268],[1354,250],[1361,263],[1338,279],[1298,274],[1404,258],[1416,255],[1427,260],[1398,273],[1411,278],[1432,282]];
for(const [x,y] of pixels){
  await evaluate(`document.querySelector('.atlas-world').dataset.rawPickState=''`);
  await send('Input.dispatchMouseEvent',{type:'mousePressed',x,y,button:'left',buttons:1,clickCount:1});
  await send('Input.dispatchMouseEvent',{type:'mouseReleased',x,y,button:'left',buttons:0,clickCount:1});
  await sleep(200);
  samples.push({pixel:[x,y],raw:await evaluate(`(()=>{const value=document.querySelector('.atlas-world')?.dataset.rawPickState;try{return JSON.parse(value||'null')}catch{return value||null}})()`)});
}
const state=await evaluate(`(()=>{try{return JSON.parse(document.querySelector('.atlas-world')?.dataset.sceneState||'null')}catch{return null}})()`);
const report={status:'runtime-source-hit-diagnostic',checkedAt:new Date().toISOString(),runtime:base,chosen,screenshot,prePickState,state,samples,limitations:['Pixel hits identify current visible runtime source ownership. Component closure and removal approval remain separate source-geometry checks.']};
const output='docs/source-evidence-v4/ivillage-remnants/ivillage-sky-floater-picks-u73.json';
await fs.writeFile(path.join(root,output),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({output,screenshot,camera:state?.camera,target:state?.target,samples},null,2));
socket.close();
