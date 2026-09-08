#!/usr/bin/env python3
"""Select, copy and verify complete independent campus project checkpoints."""
import argparse, hashlib, json, os, re, shutil, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CATALOG=ROOT/'versions/catalog.json'
GENERATED={'.git','node_modules','dist','out','.next','.vinext','.preview','.local','.wrangler','__pycache__'}
def catalog(): return json.loads(CATALOG.read_text())
def selected(version=None):
    data=catalog(); name=version or data['latest']
    if name not in {v['id'] for v in data['versions']}: raise ValueError('Unknown version: '+name)
    p=ROOT/'versions'/name
    if p.is_symlink() or not p.is_dir():raise ValueError('Missing or linked version: '+name)
    return p

def files(root):
    for directory, dirs, names in os.walk(root,followlinks=False):
        for name in dirs+names:
            if (Path(directory)/name).is_symlink():raise ValueError('Linked file in version: '+str(Path(directory)/name))
        dirs[:]=[d for d in dirs if d not in GENERATED]
        for name in sorted(names):
            if name in {'.DS_Store','INVENTORY.local.json'} or name.startswith('._') or name.endswith(('.pyc','.tsbuildinfo')):continue
            yield Path(directory)/name

def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def inventory(root):
    return {str(p.relative_to(root)):{'bytes':p.stat().st_size,'sha256':digest(p)} for p in sorted(files(root))}
def seal(root):
    items=inventory(root)
    (root/'INVENTORY.local.json').write_text(json.dumps({'version':root.name,'files':items},indent=2)+'\n')
    return items

def fork(source,name):
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{2,79}',name):raise ValueError('Use a dated lowercase version ID')
    target=ROOT/'versions'/name
    if target.exists():raise ValueError('Version already exists; never overwrite a checkpoint')
    before=seal(source)
    temporary=ROOT/'versions'/('.copy-'+name)
    if temporary.exists():raise ValueError('Previous partial copy exists: '+str(temporary))
    temporary.mkdir()
    for p in files(source):
        dest=temporary/p.relative_to(source);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
    if inventory(temporary)!=before:raise ValueError('Copy verification failed; latest was not changed')
    meta=json.loads((temporary/'VERSION.json').read_text());meta.update(id=name,parent=source.name,status='current',projectDate=name[:10])
    (temporary/'VERSION.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
    temporary.rename(target);seal(target)
    data=catalog();data['versions'].append({'id':name,'path':name,'kind':meta['kind']});data['latest']=name
    tmp=CATALOG.with_suffix('.tmp');tmp.write_text(json.dumps(data,indent=2)+'\n');os.replace(tmp,CATALOG)
    print('Created independent copy and selected latest:',target)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--version')
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('list');sub.add_parser('seal');sub.add_parser('verify');sub.add_parser('path')
    sub.add_parser('fork').add_argument('id')
    sub.add_parser('exec').add_argument('args',nargs=argparse.REMAINDER)
    a=parser.parse_args();root=selected(a.version)
    if a.command=='list':print(json.dumps(catalog(),indent=2))
    elif a.command=='path':print(root)
    elif a.command=='fork':fork(root,a.id)
    elif a.command=='seal':print('Sealed',len(seal(root)),'files in',root)
    elif a.command=='verify':
        expected=json.loads((root/'INVENTORY.local.json').read_text())['files'];actual=inventory(root)
        if actual!=expected:
            changed=sorted(k for k in set(expected)|set(actual) if expected.get(k)!=actual.get(k))
            raise ValueError('Checkpoint differs: '+', '.join(changed[:20]))
        print('Verified',len(actual),'independent files in',root)
    else:
        args=a.args[1:] if a.args[:1]==['--'] else a.args
        if not args:raise ValueError('Provide a command to run in the selected version')
        raise SystemExit(subprocess.run(args,cwd=root).returncode)
if __name__=='__main__':
    try:main()
    except (ValueError,OSError) as e:raise SystemExit(str(e))
