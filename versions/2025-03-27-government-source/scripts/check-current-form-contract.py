#!/usr/bin/env python3
"""Negative checks against an isolated copy of the actual complete Hall set."""
import copy
import json
import struct
import tempfile
from pathlib import Path
from current_form_contract import validate_current_form_set, sha

P = Path(__file__).resolve().parents[1]
registry = json.loads((P/'public/data/entity-registry.json').read_text())
entity = next(e for e in registry['entities'] if e['entityId'] == 'building:691adb789d35c25557ecab1f')
rep = next(r for r in entity['representations'] if r.get('subtype') == 'unified_current_form_approximation')
actual_base = P/'public/models/current-forms/ivillage-rebuild'
manifest = json.loads((actual_base/'manifest.json').read_text())
checks = []
with tempfile.TemporaryDirectory(prefix='current-form-contract-') as temporary:
    root = Path(temporary); public = root/'public'; public.mkdir()
    for name in ('data', 'interiors'):
        (public/name).symlink_to(P/'public'/name, target_is_directory=True)
    base = public/'models/current-forms/ivillage-rebuild'; base.mkdir(parents=True)
    for name in ('textures', 'references'):
        if (actual_base/name).exists():(base/name).symlink_to(actual_base/name, target_is_directory=True)
    (base/manifest['asset']['url']).symlink_to(actual_base/manifest['asset']['url'])

    def run(name, mutate, expected=None):
        m, e, r = copy.deepcopy(manifest), copy.deepcopy(entity), copy.deepcopy(rep)
        mutate(m,e,r)
        (base/'manifest.json').write_text(json.dumps(m))
        try:validate_current_form_set(root,e,r)
        except (ValueError,KeyError,StopIteration) as error:
            assert expected and expected in str(error), (name,error)
            checks.append({'name':name,'rejected':str(error)})
        else:
            assert expected is None, name+' unexpectedly accepted'
            checks.append({'name':name,'status':'pass'})

    run('Actual packed asset and public source files',lambda m,e,r:None)
    run('Old representation points to stale GLB',lambda m,e,r:r.update(asset='/models/old.glb'),'different model')
    run('Wrong physical building binding',lambda m,e,r:r.update(featureId='wrong-building'),'physical member binding')
    run('Source floor Z changed in metadata',lambda m,e,r:m['members'][0]['sourceFloors'][0].update(sourceZValues=[-999]),'reference/Z changed')
    run('Public source floor SHA changed',lambda m,e,r:m['members'][0]['sourceFloors'][0].update(sha256='0'*64),'source floor SHA changed')
    run('Approximate roof promoted to measured',lambda m,e,r:m['accuracy'].update(measuredRoofHeight=True),'promoted to survey')
    run('Missing member in declared set',lambda m,e,r:m['members'].pop(),'root coverage')
    run('Different embedded photograph metadata',lambda m,e,r:m['appearanceTextures'][0].update(sha256='0'*64),'photographic metadata mismatch')

    def shifted_bounds(m,e,r):
        m['members'][0]['bounds']['max'][0] += 5
        r['bounds'] = copy.deepcopy(m['members'][0]['bounds'])
    run('Matching manifest and registry cannot hide shifted actual bounds',shifted_bounds,'actual root bounds differ')

    raw = bytearray((actual_base/manifest['asset']['url']).read_bytes())
    length = struct.unpack_from('<I',raw,12)[0]; g=json.loads(raw[20:20+length])
    node=g['nodes'][g['nodes'][g['scenes'][0]['nodes'][0]]['children'][0]]
    primitive=g['meshes'][node['mesh']]['primitives'][0]
    accessor=g['accessors'][primitive['attributes']['POSITION']]; view=g['bufferViews'][accessor['bufferView']]
    start=28+length+view.get('byteOffset',0)+accessor.get('byteOffset',0)
    stride=view.get('byteStride',12); raw[start+stride:start+stride+12]=raw[start:start+12]
    (base/'degenerate.glb').write_bytes(raw)
    def degenerate(m,e,r):
        m['asset']={'url':'degenerate.glb','bytes':len(raw),'sha256':sha(raw)}
        r['asset']=str(Path(r['sourceManifest']).parent/'degenerate.glb')
    run('Rehashed GLB containing collapsed actual triangle',degenerate,'degenerate packed triangle')

report={'status':'pass','checks':checks,'sourceAssetSHA256':manifest['asset']['sha256'],
        'originalPublicFilesModified':0,'visualAcceptance':False}
(P/'docs/source-evidence-v4/current-form-contract-tests.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
