import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const port=Number(process.env.HKUST_CDP_PORT||9333);
const base='http://127.0.0.1:4317/';
const output=path.join(root,'docs/screenshots/v4/building-neighborhood-u68');
const reportPath=path.join(root,'docs/source-evidence-v4/building-quality/building-neighborhood-runtime-u68.json');
const samples=[
  ['hall-2','本科生宿舍2座'],
  ['hall-4','本科生宿舍4座'],
  ['staff-apartments-1-12','教职员宿舍公寓1-12号'],
  ['hall-2-return','本科生宿舍2座'],
];
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const pages=await (await fetch(`http://127.0.0.1:${port}/json`)).json();
const page=pages.find(item=>item.type==='page'&&item.url.startsWith(base));
if(!page)throw new Error(`No ${base} page on CDP port ${port}`);
const socket=new WebSocket(page.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
let nextId=0;
const pending=new Map();
socket.addEventListener('message',event=>{
  const message=JSON.parse(String(event.data));
  if(!message.id||!pending.has(message.id))return;
  const target=pending.get(message.id);pending.delete(message.id);
  if(message.error)target.reject(new Error(JSON.stringify(message.error)));else target.resolve(message.result);
});
const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++nextId;pending.set(id,{resolve,reject});socket.send(JSON.stringify({id,method,params}));});
const evaluate=async expression=>{
  const result=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true,userGesture:true});
  if(result.exceptionDetails)throw new Error(JSON.stringify(result.exceptionDetails));
  return result.result.value;
};
const sceneState=()=>evaluate(`(()=>{try{return JSON.parse(document.querySelector('.atlas-world')?.dataset.sceneState||'null')}catch{return null}})()`);
await fs.mkdir(output,{recursive:true});
await evaluate(`localStorage.setItem('hkust-map-locale','zh-Hans');localStorage.setItem('hkust-map-quality','ultra');location.reload();true`);
await sleep(12000);
const rows=[];
for(const [slug,query] of samples){
  const chosen=await evaluate(`(async()=>{
    const input=document.querySelector('input[aria-label="搜索校园实体"]');
    if(!input)return {ok:false,error:'search-input-missing'};
    const setter=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;
    setter.call(input,${JSON.stringify(query)});input.dispatchEvent(new Event('input',{bubbles:true}));
    await new Promise(r=>setTimeout(r,700));
    const buttons=[...document.querySelectorAll('.entity-results>button')];
    const button=buttons.find(b=>(b.querySelector('strong')?.textContent||'').includes(${JSON.stringify(query)}));
    if(!button)return {ok:false,error:'result-missing',results:buttons.map(b=>b.querySelector('strong')?.textContent||'')};
    const label=button.querySelector('strong')?.textContent||'';button.click();return {ok:true,label};
  })()`);
  if(!chosen.ok){rows.push({slug,query,chosen});continue;}
  await sleep(5000);
  for(let i=0;i<4;i++){
    await send('Input.dispatchMouseEvent',{type:'mouseWheel',x:900,y:500,deltaX:0,deltaY:-400});
    await sleep(150);
  }
  await sleep(18000);
  const settled=await sceneState();
  const ui=await evaluate(`({card:document.querySelector('.entity-card h2')?.textContent||'',status:document.querySelector('.world-status')?.textContent||'',quality:localStorage.getItem('hkust-map-quality')})`);
  const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
  const screenshot=`docs/screenshots/v4/building-neighborhood-u68/${slug}-near-ultra.png`;
  await fs.writeFile(path.join(root,screenshot),Buffer.from(shot.data,'base64'));
  rows.push({slug,query,chosen,ui,screenshot,settled});
  console.log(`${slug}: ${ui.card||chosen.label}`);
}
const report={
  status:rows.every(row=>row.chosen?.ok&&row.settled)?'captured':'partial',
  checkedAt:new Date().toISOString(),runtime:base,
  viewport:{width:1440,height:1000,deviceScaleFactor:1},requestedQuality:'ultra',
  settle:{focusMs:5000,nearMs:18600,wheelEvents:4,wheelDeltaY:-400,wheelPointCss:[900,500]},
  method:'Production search selection and fixed natural wheel zoom in a real Chrome WebGL page. Hall II is revisited after two distant regions.',
  rows,
  limitations:['Screenshots establish this camera route and observed runtime state; they are not a final all-campus visual acceptance.','A terminal source can preserve source-era blur or obsolete construction geometry; zero runtime errors do not prove current visual accuracy.'],
};
await fs.mkdir(path.dirname(reportPath),{recursive:true});
await fs.writeFile(reportPath,JSON.stringify(report,null,2)+'\n');
console.log(reportPath);
socket.close();
