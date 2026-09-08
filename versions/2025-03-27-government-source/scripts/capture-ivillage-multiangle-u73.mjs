import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const port=Number(process.env.HKUST_CDP_PORT||9222);
const base='http://127.0.0.1:4317/';
const output=path.join(root,'docs/screenshots/v4/ivillage-multiangle-u73');
const reportPath=path.join(root,'docs/source-evidence-v4/ivillage-remnants/ivillage-multiangle-runtime-u73.json');
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const pages=await (await fetch(`http://127.0.0.1:${port}/json`)).json();
const page=pages.find(item=>item.type==='page'&&item.url.startsWith(base));
if(!page)throw new Error(`No ${base} page on CDP port ${port}`);
const socket=new WebSocket(page.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
let nextId=0;const pending=new Map();
socket.addEventListener('message',event=>{const message=JSON.parse(String(event.data));if(!message.id||!pending.has(message.id))return;const target=pending.get(message.id);pending.delete(message.id);message.error?target.reject(new Error(JSON.stringify(message.error))):target.resolve(message.result);});
const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++nextId;pending.set(id,{resolve,reject});socket.send(JSON.stringify({id,method,params}));});
const evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true,userGesture:true});if(result.exceptionDetails)throw new Error(JSON.stringify(result.exceptionDetails));return result.result.value;};
const state=()=>evaluate(`(()=>{try{return JSON.parse(document.querySelector('.atlas-world')?.dataset.sceneState||'null')}catch{return null}})()`);
await fs.mkdir(output,{recursive:true});
const chosen=await evaluate(`(async()=>{document.getElementById('qa-u73-hide')?.remove();const input=document.querySelector('input[aria-label="搜索校园实体"]');if(!input)return {ok:false,error:'search-input-missing'};const setter=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;setter.call(input,'本科生宿舍12座');input.dispatchEvent(new Event('input',{bubbles:true}));await new Promise(r=>setTimeout(r,700));const button=[...document.querySelectorAll('.entity-results>button')].find(b=>(b.querySelector('strong')?.textContent||'').includes('本科生宿舍12座'));if(!button)return {ok:false,error:'result-missing'};button.click();return {ok:true,label:button.querySelector('strong')?.textContent||''}})()`);
if(!chosen.ok)throw new Error(JSON.stringify(chosen));
await sleep(12000);
await evaluate(`(()=>{const style=document.createElement('style');style.id='qa-u73-hide';style.textContent='.topbar,.rail,.detail-card,.view-heading,.scene-controls,.map-bottom,.load-status{display:none!important}.workspace{height:100dvh!important}.map-workspace{width:100vw!important}';document.head.append(style);return true})()`);
await sleep(2500);
const rows=[];
for(let angle=0;angle<4;angle++){
  if(angle){
    await send('Input.dispatchMouseEvent',{type:'mousePressed',x:720,y:500,button:'left',buttons:1,clickCount:1});
    await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:1030,y:475,button:'left',buttons:1});
    await send('Input.dispatchMouseEvent',{type:'mouseReleased',x:1030,y:475,button:'left',buttons:0,clickCount:1});
    await sleep(8500);
  }
  const settled=await state();
  const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
  const screenshot=`docs/screenshots/v4/ivillage-multiangle-u73/hall12-angle-${angle+1}.png`;
  await fs.writeFile(path.join(root,screenshot),Buffer.from(shot.data,'base64'));
  rows.push({angle:angle+1,screenshot,settled});
  console.log(`angle-${angle+1}`);
}
const report={status:'captured',checkedAt:new Date().toISOString(),runtime:base,quality:'ultra',selected:chosen,method:'Real Chrome WebGL production selection followed by three production left-drag orbit gestures; UI hidden after selection only to expose the full rendered canvas.',rows,limitations:['Four visual directions around the Hall XII focus do not prove every hidden component absent.','No source component is deleted without matching visible-pixel or owner evidence.']};
await fs.writeFile(reportPath,JSON.stringify(report,null,2)+'\n');
console.log(reportPath);socket.close();
