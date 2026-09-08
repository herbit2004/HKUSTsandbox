#!/usr/bin/env python3
"""Install independently checked native partitions without rewriting their payloads.

The previous regional manifest is retained as evidence, not as overlapping live
owners. This only prepares public assets; preview publication is a separate step.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / 'public/models/hires'
EVIDENCE = ROOT / 'docs/source-evidence-v4/native-corridor'


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def install(source, relative, expected):
    assert digest(source) == expected, f'Payload SHA mismatch: {source}'
    destination = PUBLIC / relative
    if destination.exists():
        assert digest(destination) == expected, f'Refusing to overwrite different payload: {destination}'
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    assert digest(destination) == expected
    return relative.as_posix()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', type=Path)
    args = parser.parse_args()
    staged = read(args.stage / 'staged-partitions.json')
    checked = read(args.stage / 'independent-validation.json')
    roads = read(args.stage / 'road-protection.json')
    patches = copy.deepcopy(staged['patches'])
    assert checked['status'] == 'pass' and checked['mismatches'] == 0
    assert checked['stageSha256'] == digest(args.stage / 'staged-partitions.json'), 'Validation belongs to another staging revision'
    assert roads['stageSha256'] == checked['stageSha256'], 'Road metadata belongs to another staging revision'
    assert checked['partitionCount'] == len(patches)
    validated = {(r['id'], r['level']): r for r in checked['rows']}
    assert checked['levelCount'] == len(checked['rows']) == len(validated) == 2 * len(patches)
    assert len({p['id'] for p in patches}) == len(patches)
    known = {p['id'] for p in patches}
    for cluster in roads['clusters']:
        assert set(cluster['partitionIds']) <= known, cluster['id']
    # Do not let the temporary terminal-only staging schema silently replace
    # the previous, cheaper complete high frontier at distant views.
    for patch in patches:
        assert set(patch['levels']) == {'high', 'fine'}, patch['id']
        for name, level in patch['levels'].items():
            assert validated[(patch['id'], name)]['maskSha256'] == level['mask']['sha256'], 'Unvalidated level mask'
            assert level['completeSelectedSubtree'] is True, 'Partial tree would omit another surface stratum'
        assert all(t.get('originalError', t.get('geometricError')) == 0
                   for t in patch['levels']['fine']['tiles']), patch['id']

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    prior = EVIDENCE / 'previous-regional-manifest.json'
    if not prior.exists():
        shutil.copy2(PUBLIC / 'manifest.json', prior)
    original = read(prior)
    assert not (set(p['id'] for p in original['patches']) & known), 'Old regional and new partition owners must remain distinct'
    files = {}
    source_ids = {}
    for patch in patches:
        for level_name, level in patch['levels'].items():
            for tile in level['tiles']:
                path = Path(tile['url'])
                source = path if path.is_absolute() else PUBLIC / path
                relative = Path('native-corridor/source') / (tile['id'] + '.glb') if path.is_absolute() else path
                tile['url'] = install(source, relative, tile['sha256'])
                files[tile['url']] = tile['sha256']
                owner = source_ids.setdefault(tile['id'], patch['id'])
                assert owner == patch['id'], f'Tile occurs in multiple live owners: {tile["id"]}'
            level['bytes'] = sum(t['bytes'] for t in level['tiles'])
            level['textureBytes'] = sum(t['textureBytes'] for t in level['tiles'])
            level['textureMipBytes'] = sum(t['textureMipBytes'] for t in level['tiles'])
            level['triangles'] = sum(t['triangles'] for t in level['tiles'])
            mask = copy.deepcopy(level.get('mask', patch.get('mask')))
            assert mask is not None, f'Partition needs exact source mask: {patch["id"]}/{level_name}'
            source = Path(mask['url'])
            if not source.is_absolute():
                source = args.stage / source
            relative = Path('native-corridor/masks') / (patch['id'] + '-' + level_name + '.png')
            mask['url'] = install(source, relative, mask['sha256'])
            level['mask'] = mask
            files[mask['url']] = mask['sha256']
        patch['mask'] = copy.deepcopy(patch['levels']['high']['mask'])
        patch['sourceManifest'] = 'native-corridor/descriptors/' + patch['id'] + '.json'
        write(PUBLIC / patch['sourceManifest'], patch)

    manifest = {**original, 'patches': patches}
    manifest['replacementPolicy'] = 'One source-tree partition owner per actual L18 subtree; complete high/fine source frontiers replace atomically with their own exact projection mask. Previous regional owners are archived, never requested alongside their descendants. Native road coverage reserves the fine frontier in the current nearby view.'
    manifest['nativeCorridorEvidence'] = 'docs/source-evidence-v4/native-corridor/integration.json'
    write(PUBLIC / 'native-corridor/manifest.json', {'patches': patches})
    write(PUBLIC / 'road-protection.json', roads)
    write(PUBLIC / 'manifest.json', manifest)
    for name in ['independent-validation.json', 'coverage-and-costs.json', 'road-protection.json']:
        shutil.copy2(args.stage / name, EVIDENCE / name)
    report = {
        'status': 'Source assets installed; real browser acceptance pending.',
        'stageSha256': checked['stageSha256'],
        'previousManifestSha256': digest(prior),
        'previousRegionalOwners': [p['id'] for p in original['patches']],
        'livePartitionOwners': len(patches),
        'uniqueSourceTiles': len(source_ids),
        'sourceAndMaskFilesVerified': len(files),
        'files': files,
        'manifestSha256': digest(PUBLIC / 'manifest.json'),
        'sourceGeometryUvAndImagePayloadsUnchanged': True,
        'previousRegionalOwnersAbsentFromLiveManifest': not (set(p['id'] for p in original['patches']) & known),
        'limits': 'Mask and source integrity do not prove visible road decks, portal openings, camera passage or acceptable photographic quality. Dynamic texture budgets exclude fixed assets, CPU images, geometry and driver overhead.',
    }
    write(EVIDENCE / 'integration.json', report)
    print(json.dumps({k: v for k, v in report.items() if k != 'files'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
