import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import ts from 'typescript';

const path=new URL('../app/quality.ts',import.meta.url);
const compiled=ts.transpileModule(fs.readFileSync(path,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const qualityModule={exports:{}};
vm.runInNewContext(compiled,{exports:qualityModule.exports});
const {AutomaticQuality,initialQualityLevel,qualityProfiles}=qualityModule.exports;
const results=[];
function test(name,body){body();results.push({name,passed:true});}
test('hardware ceiling remains independent of upload errors',()=>{
 assert.equal(initialQualityLevel(10,16384),'high');
 assert.equal(initialQualityLevel(4,16384),'smooth');
 assert.equal(initialQualityLevel(6,8192),'balanced');
});
test('finite construction and upload spikes do not permanently downgrade',()=>{
 const q=new AutomaticQuality('high');
 for(let i=0;i<2000;i++)q.observe(70,20000+i*17,false);
 for(let i=0;i<1000;i++)q.observe(6,55000+i*17,true);
 assert.equal(q.level,'high');assert.ok(q.stats().eligible);
});
test('sustained slow rendering still lowers quality',()=>{
 const q=new AutomaticQuality('high');
 for(let i=0;i<180;i++)q.observe(40,20000+i*17,true);
 assert.equal(q.level,'balanced');
 for(let i=0;i<180;i++)q.observe(40,40000+i*17,true);
 assert.equal(q.level,'smooth');
});
test('stable recovery is delayed and bounded by original hardware ceiling',()=>{
 const q=new AutomaticQuality('high');
 for(let i=0;i<180;i++)q.observe(40,20000+i*17,true);
 for(let i=0;i<900;i++)q.observe(4,30000+i*17,true);
 assert.equal(q.level,'balanced');
 for(let i=0;i<1800;i++)q.observe(4,70000+i*17,true);
 assert.equal(q.level,'high');
 for(let i=0;i<10000;i++)q.observe(4,120000+i*17,true);
 assert.equal(q.level,'high');
});
test('manual quality profiles retain distinct source and display budgets',()=>{
 const names=['smooth','balanced','high','ultra'];
 for(let i=1;i<names.length;i++){
  assert.ok(qualityProfiles[names[i]].meshMiB>qualityProfiles[names[i-1]].meshMiB);
  assert.ok(qualityProfiles[names[i]].dpr>qualityProfiles[names[i-1]].dpr);
 }
 assert.ok(qualityProfiles.ultra.meshFine);
});
test('actual scene resize resamples display DPR without changing quality or source demand',()=>{
 const source=fs.readFileSync(new URL('../app/scene.ts',import.meta.url),'utf8');
 const ast=ts.createSourceFile('scene.ts',source,ts.ScriptTarget.Latest,true);let method;
 const visit=node=>{if(ts.isMethodDeclaration(node)&&node.name.getText(ast)==='resize')method=node;ts.forEachChild(node,visit);};visit(ast);assert.ok(method);
 const out={exports:{}};const context={module:out,qualityProfiles,devicePixelRatio:.8};
 vm.runInNewContext(ts.transpileModule('module.exports=({'+method.getText(ast)+'}).resize',{compilerOptions:{target:ts.ScriptTarget.ES2022}}).outputText,context);
 let pixelRatio=.8,ratioChanges=0,sizes=0,projections=0;
 const owner={host:{clientWidth:1149,clientHeight:1079},qualityLevel:'high',renderer:{getPixelRatio:()=>pixelRatio,setPixelRatio:value=>{pixelRatio=value;ratioChanges++;},setSize:()=>sizes++},applySafeFrameProjection:()=>projections++,applyQuality:()=>assert.fail('resize must not reload source quality'),updateDetails:()=>assert.fail('resize must not request source detail')};
 out.exports.call(owner);assert.equal(pixelRatio,.8);assert.equal(ratioChanges,0);
 context.devicePixelRatio=2;out.exports.call(owner);assert.equal(pixelRatio,1.6);assert.equal(ratioChanges,1);out.exports.call(owner);assert.equal(ratioChanges,1);
 owner.qualityLevel='ultra';out.exports.call(owner);assert.equal(pixelRatio,2);assert.equal(ratioChanges,2);
 owner.host.clientWidth=0;context.devicePixelRatio=1;out.exports.call(owner);assert.equal(pixelRatio,2);assert.equal(ratioChanges,2);assert.equal(sizes,4);assert.equal(projections,4);
});
fs.writeFileSync(new URL('../docs/source-evidence-v4/quality-checks.json',import.meta.url),JSON.stringify({generatedAt:new Date().toISOString(),results},null,2)+'\n');
console.log(`${results.length}/${results.length} quality checks passed`);
