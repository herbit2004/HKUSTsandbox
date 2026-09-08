from pathlib import Path
import json,shutil
src=Path('/tmp/hkust-v2-pois');root=Path(__file__).resolve().parents[1]
shutil.copytree(src,root/'source-pathadvisor/v2-position-evidence',dirs_exist_ok=True)
d=json.loads((root/'public/data/catalog.json').read_text());patches=json.loads((src/'catalog-patches.json').read_text())['patches']
for patch in patches:
 b=next(b for b in d['buildings'] if b['id']==patch['id']);b.update(patch['set'])
 for key in patch['unset']:b.pop(key,None)
(root/'public/data/catalog.json').write_text(json.dumps(d,ensure_ascii=False,separators=(',',':')))
shutil.copy2(src/'building-footprints.json',root/'public/data/building-footprints.json')
print('Applied',len(patches),'evidence-backed patches')
