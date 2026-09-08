#!/usr/bin/env python3
"""Integrity/manifest checks for the independent environment candidate."""
import hashlib,json,struct
from pathlib import Path
P=Path(__file__).resolve().parents[1]/'public/models/current-forms/ivillage-rebuild/environment-candidate'
m=json.loads((P/'manifest.json').read_text()); raw=(P/m['asset']['url']).read_bytes()
assert hashlib.sha256(raw).hexdigest()==m['asset']['sha256']
magic,version,total=struct.unpack_from('<4sII',raw); assert (magic,version,total)==(b'glTF',2,len(raw))
assert m['id'].endswith('-v2') and m['asset']['members'][0]['triangles']>0
assert len(m['features'])==3 and m['noPreviewPublication']
assert set(m['limitations']) >= {'roads','trees/canopy','Hall X-XIII masks','sports-court boundary'}
assert all(u.startswith('https://cdo.hkust.edu.hk/') for u in m['source'][1:])
report={'status':'pass','assetSHA256':m['asset']['sha256'],'bytes':len(raw),'triangles':m['asset']['members'][0]['triangles'],'features':[x['name'] for x in m['features']],'limitations':m['limitations'],'visualQA':'offline review uses existing four current-form previews; no browser preview published'}
print(json.dumps(report,ensure_ascii=False,indent=2))
(P/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
