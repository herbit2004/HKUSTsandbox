#!/usr/bin/env python3
"""Bind reviewed complete-set assets to the existing physical entities.

Does not create buildings/floors or alter their names, IDs, relations or source
geometry. The one missing Hall X representation is attached to its existing ID.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path
from current_form_contract import image_dimensions


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folders', nargs='+', help='Existing folders under public/models/current-forms')
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    public = project / 'public'
    registry_path = public / 'data/entity-registry.json'
    registry = json.loads(registry_path.read_text())
    entities = {e['entityId']: e for e in registry['entities']}
    floors = json.loads((public / 'interiors/manifest.json').read_text())['floors']
    changes = []
    for folder in args.folders:
        base = public / 'models/current-forms' / folder
        manifest_path = base / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        assert manifest['version'] == 1 and manifest['members']
        raw = (base / manifest['asset']['url']).read_bytes()
        assert digest(base / manifest['asset']['url']) == manifest['asset']['sha256']
        length = struct.unpack_from('<I', raw, 12)[0]
        g = json.loads(raw[20:20+length]); binary = raw[28+length:]
        # Match actual embedded bytes to a saved local photographic input/output.
        image_files = [p for sub in ('textures', 'references') for p in (base/sub).glob('*') if p.suffix.lower() in ('.png', '.jpg', '.jpeg')]
        by_sha = {digest(p): p for p in image_files}
        manifest['appearanceTextures'] = []
        for image in g['images']:
            view = g['bufferViews'][image['bufferView']]
            data = binary[view.get('byteOffset',0):view.get('byteOffset',0)+view['byteLength']]
            sha = hashlib.sha256(data).hexdigest(); path = by_sha[sha]
            width, height = image_dimensions(data)
            w, h, mip = width, height, 0
            while True:
                mip += w*h*4
                if w == h == 1:break
                w, h = max(1,w//2), max(1,h//2)
            manifest['appearanceTextures'].append({'asset': str(path.relative_to(base)), 'sha256': sha,
                'dimensions': [width,height], 'bytes': len(data), 'baseRGBABytes': width*height*4,
                'rgbaWithMipBytes': mip, 'embeddedByteEqual': True})
        manifest['accuracy'] = {'measuredExterior': False, 'measuredRoofHeight': False,
            'unphotographedElevations': 'Reuse inspected photographic material families; full camera registration unavailable',
            'publicFloorGeometry': 'Original source files and source Z retained separately from the exterior root'}
        source_paths = {'/data/building-footprints.json', '/interiors/manifest.json'}
        for member in manifest['members']:
            entity = entities[member['entityId']]
            assert entity['externalIds']['pathAdvisorBuildingId'] == member['buildingId']
            member_floors = [f for f in floors if f['buildingId'] == member['buildingId']]
            member['sourceFloors'] = [{'id': f['id'], 'asset': '/interiors/'+f['url'],
                'sha256': digest(public/'interiors'/f['url']), 'sourceZValues': f['sourceZValues']} for f in member_floors]
            source_paths.update(f['asset'] for f in member['sourceFloors'])
            prior = [r for r in entity['representations'] if 'current_form' in r.get('subtype','')]
            assert len(prior) <= 1
            representation = prior[0] if prior else {'id': 'rep:current-form:'+member['nodeName'], 'type': 'mesh', 'sourceId':'hkust-current-form-2026'}
            previous = dict(representation)
            representation.update({'subtype':'unified_current_form_approximation',
                'asset': str(Path('/models/current-forms')/folder/manifest['asset']['url']),
                'sourceManifest': str(Path('/models/current-forms')/folder/'manifest.json'),
                'nodeName': member['nodeName'], 'featureId': member['buildingId'], 'bounds': member['bounds'],
                'sourceZValues': sorted({z for f in member_floors for z in f['sourceZValues']}),
                'registration':'Complete local building root; photographic UV/materials and structural approximation use the same representation-set contract. Original public floors are separate.'})
            if not prior:entity['representations'].append(representation)
            changes.append({'entityId': entity['entityId'], 'previousRepresentation': previous,
                'representation': dict(representation), 'assetSHA256': manifest['asset']['sha256']})
        manifest.setdefault('sources', {})['savedGeometry'] = [{'asset': asset, 'sha256': digest(public/asset.lstrip('/'))} for asset in sorted(source_paths)]
        manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    registry['counts']['representations'] = sum(len(e['representations']) for e in registry['entities'])
    registry['counts']['currentFormModels'] = sum('current_form' in r.get('subtype','') for e in registry['entities'] for r in e['representations'])
    registry_path.write_text(json.dumps(registry,ensure_ascii=False,indent=2)+'\n')
    report = {'changes':changes,'physicalEntitiesCreated':0,'publicFloorFilesModified':0,
        'status':'Data registration complete; offline and live acceptance separate'}
    (project/'docs/source-evidence-v4/current-form-registration.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'registeredMembers':len(changes),'currentFormModels':registry['counts']['currentFormModels'],'physicalEntitiesCreated':0}))


if __name__ == '__main__':
    main()
