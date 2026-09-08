#!/usr/bin/env python3
"""Build only catalog.latest; keep full runtime bytes separate from the small Sites archive."""
import argparse, hashlib, json, mimetypes, shutil, subprocess, tempfile
from pathlib import Path
from versions import ROOT, selected, dependency_cache

def files(directory):
    return sorted(p for p in directory.rglob('*') if p.is_file() and p.name!='.DS_Store' and not p.name.startswith('._') and '__pycache__' not in p.parts)
def digest(p):
    with p.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def copy(source,target):
    if source.is_symlink():raise ValueError('Runtime links are not permitted: '+str(source))
    target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
def main():
    source=selected(); profile=json.loads((source/'public/data/dataset-profile.json').read_text())['id']
    if profile!='full-local':raise ValueError('Private full Sites deployment requires the latest full-local checkpoint')
    local=ROOT/'.local';local.mkdir(exist_ok=True)
    deps=dependency_cache(source)
    if not (deps/'.bin/vinext').exists():raise ValueError('Install locked dependencies with npm ci first')
    with tempfile.TemporaryDirectory(prefix='sites-build-',dir=local) as temp:
        stage=Path(temp)
        for directory in ['app','components','hooks','lib','sites']:
            for p in files(source/directory):copy(p,stage/p.relative_to(source))
        for name in ['package.json','package-lock.json','vite.config.ts','next.config.ts','tsconfig.json','next-env.d.ts']:
            copy(source/name,stage/name)
        for p in files(source/'public'):copy(p,stage/p.relative_to(source))
        copy(ROOT/'scripts/sites-worker.vite.mjs',stage/'scripts/sites-worker.vite.mjs')
        copy(ROOT/'.openai/hosting.json',stage/'.openai/hosting.json')
        inventory={str(p.relative_to(stage/'public')):{'bytes':p.stat().st_size,'sha256':digest(p)} for p in files(stage/'public')}
        # Disposable dependency cache only. No version or material links are created.
        (stage/'node_modules').symlink_to(deps,target_is_directory=True)
        subprocess.run(['npm','run','check'],cwd=stage,check=True)
        subprocess.run(['npm','run','build'],cwd=stage,check=True)
        client=stage/'dist/client'
        assert (client/'index.html').is_file()
        for name,item in inventory.items():
            p=client/name
            if not p.is_file() or p.stat().st_size!=item['bytes'] or digest(p)!=item['sha256']:raise ValueError('Changed runtime bytes: '+name)
        (client/'_sites').mkdir(exist_ok=True)
        (client/'_sites/runtime-integrity.json').write_text(json.dumps({'version':source.name,'profile':profile,'files':inventory})+'\n')
        publication=stage/'publication';publication.mkdir()
        client.rename(publication/'runtime')
        client.mkdir()
        # Preserve the last working baseline only during the first storage import.
        # Once an active manifest exists, the Worker never serves this fallback.
        fallback=ROOT/'.local/sites-out-previous'
        if (fallback/'index.html').is_file():shutil.copytree(fallback,client,dirs_exist_ok=True)
        else:(client/'index.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>HKUST</title><main><h1>HKUST</h1><p>Campus resources are being synchronized. Please refresh shortly.</p></main></html>')
        subprocess.run(['npx','--no-install','vite','build','--config','scripts/sites-worker.vite.mjs'],cwd=stage,check=True)
        if not (stage/'dist/server/index.js').is_file():raise ValueError('Worker missing')
        (stage/'dist').rename(publication/'dist')
        copy(ROOT/'.openai/hosting.json',publication/'.openai/hosting.json')
        routes={}
        for p in files(publication/'runtime'):
            name='/'+str(p.relative_to(publication/'runtime'))
            mime={'.glb':'model/gltf-binary','.gltf':'model/gltf+json','.js':'text/javascript','.mjs':'text/javascript','.json':'application/json','.css':'text/css'}.get(p.suffix,mimetypes.guess_type(name)[0] or 'application/octet-stream')
            routes[name]={'bytes':p.stat().st_size,'sha256':digest(p),'contentType':mime}
        routes['/']=routes['/index.html']
        manifest={'version':source.name,'profile':profile,'routes':routes}
        manifest['release']=hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()
        (publication/'release.json').write_text(json.dumps(manifest)+'\n')
        previous=local/'sites-out-before-r2'
        if previous.exists():shutil.rmtree(previous)
        if (ROOT/'out').exists():(ROOT/'out').rename(previous)
        publication.rename(ROOT/'out')
        report={'version':source.name,'profile':profile,'runtimeFiles':len(inventory),'runtimeBytes':sum(f['bytes'] for f in inventory.values()),'release':manifest['release'],'r2Routes':len(routes),'staticBytes':sum(p.stat().st_size for p in files(ROOT/'out/dist/client')),'packageRoot':str(ROOT/'out')}
        (local/'sites-build-validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
