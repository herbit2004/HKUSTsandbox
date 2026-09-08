"""Idempotently bind complete checked models to existing canonical entities.

No floor, room, legacy identity or source geometry is changed.
"""
import json
from pathlib import Path
from exterior_identity import exterior_entity_id, validate_exterior_identities

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / 'public/data/entity-registry.json'
registry = json.loads(path.read_text())
entities = {e['entityId']: e for e in registry['entities']}
bundles = json.loads((ROOT / 'public/models/exteriors/manifest.json').read_text())['bundles']
validate_exterior_identities(bundles)
by_entity = {}
for bundle in bundles:
    owner = exterior_entity_id(bundle)
    entity = entities[owner]
    by_entity.setdefault(owner, []).append(bundle)
    old = next((r for r in entity['representations'] if r['type'] == 'mesh_group' and r.get('featureId') == bundle['id']), None)
    objects = []
    for source in bundle['objects']:
        obj = {k: source[k] for k in ['id', 'subtype', 'ownership', 'offset', 'matrix', 'bounds', 'triangles', 'textureDecodedBytes'] if k in source}
        obj['asset'] = '/models/exteriors/' + source['url']
        objects.append(obj)
    mask = {k: v for k, v in bundle['mask'].items() if k not in ['url', 'exactUrl']}
    mask.update(asset='/models/exteriors/' + bundle['mask']['url'], exactAsset='/models/exteriors/' + bundle['mask']['exactUrl'])
    representation = {
        'id': old['id'] if old else 'rep:complete-exterior:' + bundle['id'],
        'type': 'mesh_group', 'subtype': 'exterior_bundle', 'asset': '/models/exteriors/manifest.json',
        'featureId': bundle['id'], 'objects': objects, 'mask': mask, 'bounds': bundle['bounds'],
        'sourceId': 'exteriors', 'sourceDates': bundle.get('sourceDates', {}),
        'replacement': {'atomic': True, 'maxVisibleBundles': 8, 'strategy': 'Actual projected source coverage only; complete group admission under shared texture budget.'},
    }
    if bundle.get('physicalDomainId'):
        representation['physicalDomainId'] = bundle['physicalDomainId']
    if old: old.update(representation)
    else: entity['representations'].append(representation)
for owner, groups in by_entity.items():
    entity = entities[owner]
    external = entity.setdefault('externalIds', {})
    external['exteriorBundleIds'] = [b['id'] for b in groups]
    if len(groups) == 1:
        external['exteriorBundleId'] = groups[0]['id']
    else:
        external.pop('exteriorBundleId', None)
    external['exteriorObjectIds'] = list(dict.fromkeys(o['id'] for b in groups for o in b['objects']))
    physical_domains = [b['physicalDomainId'] for b in groups if b.get('physicalDomainId')]
    if physical_domains:
        external['physicalDomainIds'] = physical_domains
    if entity['type'] == 'zone':
        # Camera framing only. Picking retains the separate exact source domains.
        entity['bounds'] = {
            'min': [min(b['bounds']['min'][axis] for b in groups) for axis in range(3)],
            'max': [max(b['bounds']['max'][axis] for b in groups) for axis in range(3)],
        }

base = '/models/current-forms/halls-current/'
manifest = json.loads((ROOT / 'public' / base.lstrip('/') / 'manifest.json').read_text())
for building in manifest['buildings']:
    entity = entities[building['entityId']]
    identifier = 'rep:photo-roof-current-form:' + building['catalogId']
    old = next((r for r in entity['representations'] if r['id'] == identifier), None)
    representation = {
        'id': identifier, 'type': 'mesh', 'subtype': 'photo_roof_based_current_form_approximation',
        'asset': base + building['url'], 'featureId': building['buildingId'], 'bounds': building['bounds'],
        'sourceId': 'hkust-current-form-2026', 'sourceManifest': base + 'manifest.json',
        'sourceZValues': building['sourceFloorZValues'],
        'sourceDates': {'statusChecked': manifest['checkedAt'], 'captureDate': None},
        'evidence': 'Approximate current appearance from official outlines, terminal source roof triangles and official photos. Original floor sources retain their own geometry and Z; roof, facade and PV are not surveyed BIM.',
    }
    if old: old.update(representation)
    else: entity['representations'].append(representation)
registry['counts']['representations'] = sum(len(e['representations']) for e in entities.values())
registry['counts']['exteriorBundleRepresentations'] = len(bundles)
registry['counts']['currentFormModels'] = 1 + len(manifest['buildings'])
path.write_text(json.dumps(registry, ensure_ascii=False, separators=(',', ':')) + '\n')
print(json.dumps({'entities':len(entities),'representations':registry['counts']['representations'],'nativeExteriorGroups':len(bundles),'currentForms':registry['counts']['currentFormModels']}))
