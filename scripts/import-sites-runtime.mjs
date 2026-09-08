// Owner-authorized private import. Tokens exist only in the process environment.
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
const origin=process.argv[2];
const access=process.env.HKUST_SITES_CHECK_TOKEN, secret=process.env.HKUST_SITE_IMPORT_TOKEN;
if(!origin||!access||!secret)throw new Error('Expected Site origin and both existing access/import tokens in environment.');
const root=new URL('../out/',import.meta.url);
const manifest=JSON.parse(fs.readFileSync(new URL('release.json',root)));
function assertLatest(){
 const latest=JSON.parse(fs.readFileSync(new URL('../versions/catalog.json',import.meta.url))).latest;
 if(latest!==manifest.version)throw new Error('Refusing stale deployment: build latest '+latest+' before importing');
}
assertLatest();
const unique=new Map();
for(const [url,entry] of Object.entries(manifest.routes))if(url!=='/'&&!unique.has(entry.sha256))unique.set(entry.sha256,{...entry,url});
async function api(endpoint,initFactory){
 for(let attempt=0;attempt<6;attempt++){
  try{
   const init=initFactory();
   const response=await fetch(new URL('/_sites/import/'+endpoint,origin),{...init,headers:{'OAI-Sites-Authorization':'Bearer '+access,'X-HKUST-Import-Token':secret,...init.headers},redirect:'error',signal:AbortSignal.timeout(240000)});
   if(!response.ok){await response.body?.cancel();throw new Error('HTTP '+response.status+' '+endpoint.slice(0,30));}
   return await response.json();
  }catch(error){if(attempt===5)throw error;await new Promise(r=>setTimeout(r,Math.min(20000,1000*2**attempt)));}
 }
}
async function pool(items,run,concurrency=32){let index=0;await Promise.all(Array.from({length:concurrency},async()=>{while(index<items.length){const item=items[index++];await run(item);}}));}
const entries=[...unique.values()];
let checked=0,lastLog=0;
async function missing(){
 const batches=[];for(let i=0;i<entries.length;i+=32)batches.push(entries.slice(i,i+32));
 const result=[];checked=0;
 await pool(batches,async batch=>{
  const r=await api('check',()=>({method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(batch.map(({sha256,bytes})=>({sha256,bytes})))}));
  result.push(...r.missing);checked+=batch.length;
  if(Date.now()-lastLog>15000){console.log('Checked '+checked+'/'+entries.length+' storage objects');lastLog=Date.now();}
 });return result;
}
const needed=await missing();const uploadTotal=needed.length;let completed=0,bytesUploaded=0;
console.log('Upload required: '+needed.length+'/'+entries.length+' unique objects');
// Check the largest asset first so a gateway body limit is discovered before a full import.
needed.sort((a,b)=>unique.get(b).bytes-unique.get(a).bytes);
async function upload(sha){
 const entry=unique.get(sha);const file=new URL('runtime/'+entry.url.slice(1),root);
 const stat=fs.statSync(file);if(stat.size!==entry.bytes)throw new Error('Local resource changed: '+entry.url);
 const hash=createHash('sha256');for await(const chunk of fs.createReadStream(file))hash.update(chunk);
 if(hash.digest('hex')!==sha)throw new Error('Local checksum changed: '+entry.url);
 const result=await api('blob/'+sha,()=>({method:'PUT',headers:{'Content-Length':String(entry.bytes),'X-Asset-Bytes':String(entry.bytes),'Content-Type':'application/octet-stream'},body:fs.createReadStream(file),duplex:'half'}));
 if(result.sha256!==sha||result.bytes!==entry.bytes)throw new Error('Upload verification failed: '+entry.url);
 completed++;bytesUploaded+=entry.bytes;
 if(Date.now()-lastLog>15000||completed===uploadTotal){console.log('Uploaded '+completed+'/'+uploadTotal+' objects; '+Math.round(bytesUploaded/1024/1024)+' MiB');lastLog=Date.now();}
}
if(needed.length)await upload(needed.shift());
await pool(needed,upload,16);
const absent=await missing();if(absent.length)throw new Error(absent.length+' resources still missing; current release was not changed');
assertLatest();
const result=await api('activate',()=>{assertLatest();return {method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(manifest)};});
if(result.release!==manifest.release)throw new Error('Unexpected activated release');
const report={version:manifest.version,release:manifest.release,routes:Object.keys(manifest.routes).length,objects:entries.length,bytesUploaded,completedAt:new Date().toISOString()};
fs.writeFileSync(new URL('../.local/sites-import-validation.json',import.meta.url),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report));
