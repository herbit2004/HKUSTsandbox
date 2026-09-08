#!/usr/bin/env python3
"""Integrate independently checked original source groups atomically.

Only exterior assets/manifest and integration evidence change. Existing groups
and the eight rendering slots remain intact; registry canonical IDs are checked.
"""
import hashlib
import argparse
import json
import shutil
from pathlib import Path
from exterior_identity import exterior_entity_id, validate_exterior_identities

P = Path(__file__).resolve().parents[1]
DEST = P / 'public/models/exteriors'
parser = argparse.ArgumentParser()
parser.add_argument('--stage', action='append')
parser.add_argument('--report', default='native-exterior-eight-group-integration.json')
args = parser.parse_args()
STAGES = [Path(p) for p in (args.stage or ['/tmp/hkust-v6-next-exteriors', '/tmp/hkust-v6-next-institutional-exteriors'])]
EVIDENCE = P / 'docs/source-evidence-v4/building-quality'
read = lambda p: json.loads(p.read_text())
digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
registry = read(P / 'public/data/entity-registry.json')
entities = {e['entityId']: e for e in registry['entities']}
manifest_path = DEST / 'manifest.json'
manifest = read(manifest_path)
validate_exterior_identities(manifest['bundles'])
original_bundles = {bundle['id']: bundle for bundle in manifest['bundles']}
before = digest(manifest_path)
bundles = {bundle['id']: bundle for bundle in manifest['bundles']}
added = []
for stage in STAGES:
    for bundle in read(stage / 'manifest.json')['bundles']:
        canonical = exterior_entity_id(bundle)
        assert canonical in entities, canonical
        assert entities[canonical]['type'] in ['building', 'zone'], canonical
        if canonical.startswith('zone:'):
            domains = read(P/'public/data/picking/building-domains-extra.json')['auditOnlyAggregateDomains']
            assert any(d['entityId'] == canonical and d['physicalDomainId'] == bundle.get('physicalDomainId') for d in domains)
            assert 'buildingId' not in bundle and all(o.get('ownership') == 'domain-only' for o in bundle['objects'])
        if bundle['id'] in original_bundles:
            assert bundle == original_bundles[bundle['id']], 'Refusing to modify an installed source bundle '+bundle['id']
        assert all(registry['legacyMap'].get(cid) == canonical for cid in bundle['catalogIds'])
        files = []
        for obj in bundle['objects']:
            source = (stage / obj['url']).parent
            target = (DEST / obj['url']).parent
            target.mkdir(parents=True, exist_ok=True)
            source_manifest = read(stage / obj['sourceManifest'])
            for item in source_manifest['files']:
                original = source / item['filename']
                destination = target / item['filename']
                assert digest(original) == item['sha256']
                if destination.exists():
                    assert digest(destination) == item['sha256'], destination
                else:
                    shutil.copy2(original, destination)
                assert digest(destination) == item['sha256']
                files.append({'path': str(destination.relative_to(P)), 'sha256': item['sha256']})
            shutil.copy2(stage / obj['sourceManifest'], DEST / obj['sourceManifest'])
        for field in ['url', 'exactUrl']:
            original = stage / bundle['mask'][field]
            destination = DEST / bundle['mask'][field]
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, destination)
            assert digest(destination) == digest(original)
        bundles[bundle['id']] = bundle
        added.append({'id': bundle['id'], 'canonicalId': canonical, 'name': entities[canonical]['name'],
            'objects': [o['id'] for o in bundle['objects']], 'originalFiles': files,
            'textureMipBytes': bundle['textureMipBytes'], 'triangles': bundle['triangles'],
            'actualDomainCoveredRatio': bundle['matchEvidence']['officialDrawingCoveredRatio']})
assert len(added) == sum(len(read(stage / 'manifest.json')['bundles']) for stage in STAGES)
manifest['bundles'] = list(bundles.values())
validate_exterior_identities(manifest['bundles'])
assert all(bundles[key] == value for key, value in original_bundles.items())
temporary = manifest_path.with_suffix('.next.json')
temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
temporary.replace(manifest_path)
(EVIDENCE / args.report).write_text(json.dumps({
    'status': 'integrated-source-validated-browser-acceptance-pending',
    'manifestSha256Before': before, 'manifestSha256After': digest(manifest_path),
    'candidateGroups': len(bundles), 'maximumIndependentReplacementSlots': 8,
    'added': added, 'runtimeFilesModified': False,
    'limits': 'Complete original source groups and masks are available for bounded view scheduling. This does not establish current-era multi-angle facade quality or loading-memory acceptance.'
}, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'groups': len(bundles), 'added': [{k: r[k] for k in ['id', 'canonicalId', 'textureMipBytes', 'triangles']} for r in added]}, indent=2))
