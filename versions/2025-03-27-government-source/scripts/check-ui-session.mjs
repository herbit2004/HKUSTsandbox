/** Exercise the actual page component handlers with deterministic React hook and
 * scene adapters. This is state/transaction coverage; browser layout and gestures
 * are separately verified by the live preview QA. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import ts from 'typescript';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const rawRegistry=JSON.parse(fs.readFileSync(path.join(root,'public/data/entity-registry.json'),'utf8'));
const rawFloors=JSON.parse(fs.readFileSync(path.join(root,'public/interiors/manifest.json'),'utf8'));
const rawResources=JSON.parse(fs.readFileSync(path.join(root,'public/data/entity-resources.json'),'utf8'));
const events=[],checks=[],hooks=[],listeners=new Map(),storage=new Map();
const documentState={documentElement:{lang:''},title:''};
let cursor=0,dirty=false,pendingEffects=[],tree,instance;
const same=(a,b)=>!!a&&!!b&&a.length===b.length&&a.every((v,i)=>Object.is(v,b[i]));
const react={
 useState(initial){const i=cursor++;if(!hooks[i])hooks[i]={value:typeof initial==='function'?initial():initial};return [hooks[i].value,value=>{hooks[i].value=typeof value==='function'?value(hooks[i].value):value;dirty=true}];},
 useRef(value){const i=cursor++;if(!hooks[i])hooks[i]={current:value};return hooks[i];},
 useMemo(fn,deps){const i=cursor++;if(!hooks[i]||!same(hooks[i].deps,deps))hooks[i]={value:fn(),deps};return hooks[i].value;},
 useCallback(fn,deps){return react.useMemo(()=>fn,deps);},
 useEffect(fn,deps){const i=cursor++;if(!hooks[i]||!same(hooks[i].deps,deps)){const old=hooks[i];hooks[i]={deps};pendingEffects.push(()=>{old?.cleanup?.();hooks[i].cleanup=fn()});}},
 useLayoutEffect(fn,deps){return react.useEffect(fn,deps);},
};
const initial={loaded:292,total:292,buildingId:'',floorId:'',loadingFloor:'',camera:[430,216,-1436],target:[336,123,-1550],detailPool:{actualBytes:1500*1048576,effectiveCapBytes:2048*1048576,targetCapBytes:1536*1048576,reducing:true},fixedResources:{estimatedTextureBytes:128*1048576}};
class Scene {
 constructor(host,registry,options){instance=this;this.host=host;this.registry=registry;this.options=options;this.opened=null;this.selectedId='';this.floorId='';this.active=true;this.showLabels=true;this.immersive=false;this.camera=[...initial.camera];this.target=[...initial.target];this.seaBlendEnabled={value:1};this.interior={setBoundary(){}};this.renderer={domElement:{focus(){events.push('focus:canvas')}}};}
 setImmersive(value){this.immersive=value;events.push('immersive:'+value);}
 setActive(value){this.active=value;events.push('active:'+value);}
 resize(){events.push('resize:'+tree.props['data-immersive']);}
 setSafeFrameInsets(insets){this.insets=insets;events.push('safeFrame:'+insets.left);}
 setLocale(value){this.locale=value;}
 setQuality(value){this.quality=value;}
 setPanMode(value){this.panMode=value;}
 clearSelection(){events.push('clearSelection');this.selectedId='';this.notify();}
 async load(){}
 dispose(){}
 notify(){this.options.change({...initial,buildingId:this.opened?.entityId||'',floorId:this.floorId,selectedId:this.selectedId});}
 async selectEntity(id){events.push('select:'+id);this.selectedId=id;const e=this.registry.get(id),floor=this.registry.floor(e);if(floor){this.opened=this.registry.building(e);this.floorId=this.registry.floorSource(floor);}this.notify();}
 async openBuilding(e){this.opened=e;this.notify();}
 closeBuilding(){this.opened=null;this.floorId='';this.notify();}
 async setFloor(id){this.floorId=id;this.notify();return true;}
 floorView(){}
 zoom(){}
 previous(){}
 preset(){}
}
const modules=new Map();
function load(name){
 if(modules.has(name))return modules.get(name);
 const extension=name==='page'?'.tsx':'.ts';
 const source=fs.readFileSync(path.join(root,'app',name+extension),'utf8');
 const out={};modules.set(name,out);
 const code=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
 vm.runInNewContext(code,{
  exports:out,console,AbortController,Map,Set,Object,Array,
  ResizeObserver:class{observe(){}disconnect(){}},
  getComputedStyle:node=>({display:node.hidden?'none':'block'}),
  document:documentState,
  localStorage:{getItem:key=>storage.get(key),setItem:(key,value)=>storage.set(key,value)},
  window:{addEventListener:(name,fn)=>{if(!listeners.has(name))listeners.set(name,new Set());listeners.get(name).add(fn);},removeEventListener:(name,fn)=>listeners.get(name)?.delete(fn)},
  fetch:async url=>({ok:true,json:async()=>url.includes('entity-registry')?rawRegistry:url.includes('interiors/manifest')?rawFloors:rawResources}),
  require(id){
   if(id==='react')return react;
   if(id==='react-dom')return {flushSync(fn){events.push('flush:start');fn();render();events.push('flush:end');}};
   if(id==='react/jsx-runtime')return {jsx:(type,props,key)=>({type,props,key}),jsxs:(type,props,key)=>({type,props,key})};
   if(id==='lucide-react')return new Proxy({},{get:(_,name)=>name});
   if(id==='./scene')return {CampusScene:Scene,initialSceneState:initial};
   if(id==='./panorama')return {default:function Panorama(){}};
   if(id.startsWith('./'))return load(id.slice(2));
   throw Error('Unexpected dependency '+id);
  },
 },{filename:name+extension});
 return out;
}
const Page=load('page').default;
function nodes(node=tree){if(!node||typeof node!=='object')return [];if(Array.isArray(node))return node.flatMap(n=>nodes(n??null));return [node,...nodes(node.props?.children??null)];}
function text(node){if(typeof node==='string'||typeof node==='number')return String(node);if(Array.isArray(node))return node.map(text).join('');return node?.props?text(node.props.children):'';}
function find(predicate){const n=nodes().find(predicate);assert.ok(n,'expected UI node');return n;}
function button(label){return find(n=>n.type==='button'&&(n.props['aria-label']===label||text(n)===label));}
function render(){cursor=0;dirty=false;tree=Page();for(const n of nodes()){if(n.props?.ref&&typeof n.props.ref==='object'){const isRail=n.type==='aside',hidden=isRail&&tree.props.className.includes('rail-closed');n.props.ref.current={hidden,offsetLeft:isRail?18:0,offsetWidth:isRail?286:1600,focus(){events.push('focus:trigger');},getClientRects(){return hidden?[]:[{}];},getBoundingClientRect(){return isRail?{left:18,right:304,width:286}:{left:0,right:1600,width:1600,height:n.type==='header'?62:900};}};}}const effects=pendingEffects;pendingEffects=[];for(const effect of effects)effect();return tree;}
async function settle(){for(let i=0;i<15;i++){await Promise.resolve();if(dirty)render();}}
async function click(label){button(label).props.onClick();await settle();}
async function choose(id){instance.options.select(id);await settle();}
async function check(name,run){await run();checks.push(name);}
function escape(){for(const fn of listeners.get('keydown')||[])fn({key:'Escape',preventDefault(){events.push('escape:prevented');}});}
render();await settle();assert.ok(instance);
await check('single HKUST identity is unchanged in all three UI languages',async()=>{
 await click('场景设置与来源');
 const expected={en:['Immersive map','Restore interface'],'zh-Hant':['沉浸地圖','恢復介面'],'zh-Hans':['沉浸地图','恢复界面']};
 for(const [locale,labels] of Object.entries(expected)){
  find(n=>n.type==='select'&&n.props.value===instance.locale).props.onChange({target:{value:locale}});await settle();
  assert.equal(text(find(n=>n.type==='h1')),'HKUST');
  await click(labels[0]);assert.equal(tree.props['data-immersive'],true);assert.equal(text(button(labels[1])),labels[1]);await click(labels[1]);assert.equal(tree.props['data-immersive'],false);
 }
});
await check('restore and Escape retain UI state, user labels, quality, language and world pose',async()=>{
 const label=find(n=>n.type==='input'&&n.props.type==='checkbox'&&n.props.checked===true);
 label.props.onChange({target:{checked:false}});await settle();assert.equal(instance.showLabels,false);
 find(n=>n.type==='select'&&n.props['aria-label']==='场景画质').props.onChange({target:{value:'ultra'}});await settle();
 await click('切换实体列表');assert.match(tree.props.className,/rail-closed/);
 await click('左键平移模式');const pose=JSON.stringify([instance.camera,instance.target]);
 for(const method of ['button','escape']){
  await click('沉浸地图');assert.equal(instance.immersive,true);assert.equal(instance.active,true);assert.equal(instance.showLabels,false);
  if(method==='button')await click('恢复界面');else{escape();await settle();}
  assert.equal(tree.props['data-immersive'],false);assert.match(tree.props.className,/rail-closed/);assert.equal(instance.showLabels,false);assert.equal(instance.quality,'ultra');assert.equal(instance.locale,'zh-Hans');assert.equal(instance.panMode,true);assert.equal(JSON.stringify([instance.camera,instance.target]),pose);assert.ok(nodes().some(n=>n.props?.className==='settings-panel'));
 }
});
await check('invalid selection stays immersive; all valid entity kinds reverse immersion then select once without resizing',async()=>{
 await click('沉浸地图');const count=events.length;await choose('missing:entity');assert.equal(tree.props['data-immersive'],true);assert.equal(events.length,count);
 const kinds=['building','floor','space','connector','facility','outdoor_area','path','zone'];
 for(const kind of kinds){
  if(!tree.props['data-immersive'])await click('沉浸地图');
  const id=rawRegistry.entities.find(e=>e.type===kind).entityId,start=events.length;
  await choose(id);const transaction=events.slice(start);
  assert.equal(tree.props['data-immersive'],false);assert.equal(transaction.filter(v=>v==='select:'+id).length,1);assert.ok(transaction.indexOf('immersive:false')<transaction.indexOf('select:'+id));assert.ok(!transaction.some(event=>event.startsWith('resize:')));
 }
});
await check('bus station row omits aggregate source-name chain without changing registry/source details',async()=>{
 const search=find(n=>n.type==='input'&&n.props['aria-label']==='搜索校园实体');search.props.onChange({target:{value:'North Bus Station'}});await settle();
 const row=find(n=>n.props?.role==='treeitem'&&text(n).includes('North Bus Station'));
 const small=nodes(row).find(n=>n.type==='small');assert.equal(text(small),'巴士站');assert.ok(small.props.title.includes(load('entity-names').entityDisplayName(instance.registry.get('zone:catalog:campus-62'),'zh-Hans')));
});
await check('indoor facility rows retain their actual building and floor across duplicate room labels',async()=>{
 const search=find(n=>n.type==='input'&&n.props['aria-label']==='搜索校园实体');search.props.onChange({target:{value:'Drinking Fountain, 2F'}});await settle();
 const names=load('entity-names');let checked=0;
 for(const row of nodes().filter(n=>n.props?.role==='treeitem')){
  const entity=instance.registry.get(row.key),building=instance.registry.building(entity),floor=instance.registry.floor(entity);
  if(!building||!floor)continue;
  const description=text(nodes(row).find(n=>n.type==='small'));
  assert.ok(description.includes(names.entityDisplayName(building,'zh-Hans')));assert.ok(description.includes(names.entityDisplayName(floor,'zh-Hans')));checked++;
 }
 assert.ok(checked>=2,'cross-building fixture must retain multiple source locations');
});
await check('entity resources replace card and preserve source aliases and known capture date',async()=>{
 await choose('facility:hkust-cwb:red-bird-sundial');await click('相关资料');
 assert.ok(!nodes().some(n=>n.props?.className==='entity-card'));
 const resourcePanel=find(n=>n.props?.className==='resource-panel');assert.match(text(resourcePanel),/The Red Bird Sundial/);assert.ok(!text(resourcePanel).includes('原始别名'));
 assert.equal(nodes(resourcePanel).filter(n=>n.type==='img').length,6);
 const imageButton=find(n=>n.type==='button'&&nodes(n).some(c=>c.type==='img'&&c.props.src.endsWith('cmo-side-a.jpg')));imageButton.props.onClick();await settle();
 assert.match(text(find(n=>n.type==='dialog')),/2004-10-26/);await click('关闭图像资料');assert.ok(nodes().some(n=>n.props?.className==='resource-panel'));await click('返回实体沙盘');assert.ok(nodes().some(n=>n.props?.className==='entity-card'));
});
await check('new outdoor entity does not inherit old open-floor photos or panoramas',async()=>{
 const indoor=rawRegistry.entities.find(e=>e.type==='space'&&e.parentId?.startsWith('floor:'));await choose(indoor.entityId);assert.ok(instance.floorId);
 await choose('facility:northbusstation');await click('相关资料');
 const panel=find(n=>n.props?.className==='resource-panel');assert.equal(nodes(panel).filter(n=>n.type==='img').length,0);assert.ok(!nodes(panel).some(n=>n.type==='button'&&/现场影像/.test(text(n))));assert.match(text(panel),/暂无已绑定/);assert.ok(text(panel).includes(load('entity-names').entityDisplayName(instance.registry.get('zone:catalog:campus-62'),'zh-Hans')));
});
await check('official map opens no phantom panel; photo return retains prior resource context',async()=>{
 await click('校园原图');assert.ok(nodes().some(n=>n.type==='dialog'));await click('关闭图像资料');assert.ok(nodes().some(n=>n.props?.className==='resource-panel'));
});
await check('locale changes preserve the current entity, floor, query, quality and pose; each translated photo return restores that resource context',async()=>{
 const {t}=load('i18n'),{entityDisplayName}=load('entity-names');
 const floor=rawRegistry.entities.find(e=>e.type==='floor'&&e.parentId==='building:691adb789d35c25557ecab1f');assert.ok(floor);
 await choose(floor.entityId);
 find(n=>n.type==='input'&&n.props['aria-label']===t(instance.locale,'搜索校园实体')).props.onChange({target:{value:'Staff Quarters'}});await settle();
 const before=JSON.stringify([instance.selectedId,instance.floorId,instance.opened.entityId,instance.camera,instance.target,instance.quality]);
 const originalInstance=instance,selectCount=events.filter(e=>e.startsWith('select:')).length;
 for(const locale of ['en','zh-Hant','zh-Hans']){
  await click(t(instance.locale,'场景设置与来源'));
  find(n=>n.type==='select'&&n.props.value===instance.locale).props.onChange({target:{value:locale}});await settle();
  assert.equal(instance,originalInstance);assert.equal(JSON.stringify([instance.selectedId,instance.floorId,instance.opened.entityId,instance.camera,instance.target,instance.quality]),before);
  assert.equal(events.filter(e=>e.startsWith('select:')).length,selectCount);
  assert.equal(find(n=>n.type==='input'&&n.props['aria-label']===t(locale,'搜索校园实体')).props.value,'Staff Quarters');
  assert.equal(documentState.documentElement.lang,locale);assert.equal(documentState.title,t(locale,'香港科技大学清水湾 · 三维校园地图'));
  assert.equal(storage.get('hkust-map-locale'),locale);
  const details=find(n=>n.type==='details'&&text(n).includes(t(locale,'来源、日期与运行详情')));
  for(const value of ['1500.0 MiB','2048 MiB','1536 MiB','128.0 MiB'])assert.ok(text(details).includes(value));
  assert.ok(text(details).includes(t(locale,'固定纹理另计约 {fixed} MiB；上述统计不含 CPU 位图、解码临时内存、几何和驱动开销。',{fixed:'128.0'})));
  await click(t(locale,'关闭设置'));await click(t(locale,'相关资料'));
  const prior=find(n=>n.props?.className==='resource-panel'),resourceIds=nodes(prior).filter(n=>n.type==='img').map(n=>n.props.src);
  assert.equal(text(nodes(prior).find(n=>n.props?.className==='eyebrow')),entityDisplayName(floor,locale));
  await click(t(locale,'校园原图'));assert.ok(nodes().some(n=>n.type==='dialog'));await click(t(locale,'关闭图像资料'));
  const returned=find(n=>n.props?.className==='resource-panel');assert.equal(text(nodes(returned).find(n=>n.props?.className==='eyebrow')),entityDisplayName(floor,locale));
  assert.deepEqual(nodes(returned).filter(n=>n.type==='img').map(n=>n.props.src),resourceIds);
  assert.equal(JSON.stringify([instance.selectedId,instance.floorId,instance.opened.entityId,instance.camera,instance.target,instance.quality]),before);
 }
});
await check('shared VIII/IX exterior exposes both original hall entities without reparenting or inventing floors',async()=>{
 await click('收起楼层');
 find(n=>n.type==='input'&&n.props['aria-label']==='搜索校园实体').props.onChange({target:{value:''}});await settle();
 const group='zone:hkust-cwb:ug-halls-8-9',members=['building:catalog:ug-hall-8','building:catalog:ug-hall-9'];
 await choose(group);
 assert.deepEqual(nodes().filter(n=>n.props?.role==='treeitem').map(n=>n.key).sort(),members);
 for(const id of members){
  const entity=instance.registry.get(id);assert.equal(entity.parentId,'campus:hkust-cwb');assert.equal(instance.registry.children.get(id)?.filter(e=>e.type==='floor').length||0,0);
  find(n=>n.props?.role==='treeitem'&&n.key===id).props.onClick();await settle();assert.equal(instance.selectedId,id);assert.equal(instance.opened,null);
  await choose(group);
 }
 assert.equal(instance.registry.zoneMembers(instance.registry.get(group)).length,2);
});
await check('card close, Escape and campus overview clear React and scene selection together',async()=>{
 const id='building:691c1c081c838d03d9a6dc21';
 for(const action of ['关闭实体信息','escape','校园全景']){
  await choose(id);assert.equal(instance.selectedId,id);assert.ok(nodes().some(n=>n.props?.className==='entity-card'));
  const clears=events.filter(e=>e==='clearSelection').length;
  if(action==='escape'){escape();await settle();}else await click(action);
  assert.equal(instance.selectedId,'');assert.equal(events.filter(e=>e==='clearSelection').length,clears+1);
  assert.ok(!nodes().some(n=>n.props?.className==='entity-card'));assert.ok(!nodes().some(n=>n.props?.role==='treeitem'&&n.props['aria-selected']));
 }
});
await check('full-width canvas remains behind the floating rail and immersion hides overlays with one restore control',()=>{
 const css=fs.readFileSync(path.join(root,'app/globals.css'),'utf8');
 assert.match(css,/\.atlas-map-region\{[^}]*position:absolute;inset:0/);assert.doesNotMatch(css,/\.atlas-app\.is-immersive>\.atlas-map-region\{[^}]*inset/);
 assert.match(css,/:not\(\.atlas-map-region\):not\(\.immersive-restore\)/);assert.match(css,/\.atlas-app\.is-immersive[^}]*\.world-labels\{pointer-events:none!important/);
 assert.equal(nodes().filter(n=>n.props?.className==='atlas-world').length,1);
 const source=fs.readFileSync(path.join(root,'app/page.tsx'),'utf8');assert.doesNotMatch(source,/requestFullscreen|exitFullscreen|fullscreenElement/);assert.ok(source.includes("select:id=>{void chooseRef.current(id)}"));
});
const report={passed:true,checks,sourceRegistryEntities:rawRegistry.entities.length,resourceCount:rawResources.resources.length,scope:'Actual current page component handlers, actual registry/floor/resource fixtures, deterministic React hook and scene adapters. CSS structure assertions only; real DOM layout, WebGL, gestures and visual restoration require live preview QA.'};
fs.mkdirSync(path.join(root,'docs/source-evidence-v4'),{recursive:true});fs.writeFileSync(path.join(root,'docs/source-evidence-v4/ui-session-tests.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report,null,2));
