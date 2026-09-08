#!/usr/bin/env python3
"""Audit saved official named-building domains; optionally merge proven identities.

Requires Shapely. No network. Reconstructs all domains from original saved GML,
including matching BUILDINGID fragments in adjacent map sheets. --apply updates
only the new identities, their reciprocal relations, and computed registry counts.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

from shapely.geometry import Polygon, Point, box, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'docs/source-evidence-v4/building-quality'
SOURCE = REPORT / 'identity-sources'
PUBLIC = ROOT / 'public/data/picking'
G = '{http://www.opengis.net/gml}'
MAP_URL = 'https://publish.ust.hk/univ/maps/Campus_Map_Color.pdf'
DOMAIN_ASSET = '/data/picking/building-domains-extra.json'


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def properties(node):
    return {c.tag.split('}')[-1]: c.text for c in node if not list(c)}


def source_parts(node):
    # Only exact straight source boundaries are accepted; no guessed arc chords.
    assert not node.findall('.//' + G + 'ArcString'), 'Unresolved source arc'
    parts = []
    for patch in node.findall('.//' + G + 'PolygonPatch'):
        rings = []
        for tag in ['exterior', 'interior']:
            for boundary in patch.findall(G + tag):
                points = []
                for segment in boundary.findall('.//' + G + 'posList'):
                    values = list(map(float, segment.text.split()))
                    assert len(values) % 3 == 0
                    for i in range(0, len(values), 3):
                        point = [values[i + 1] - 844800, 820500 - values[i]]
                        if not points or point != points[-1]:
                            points.append(point)
                assert len(points) >= 4 and points[0] == points[-1]
                rings.append(points)
        polygon = Polygon(rings[0], rings[1:])
        assert polygon.is_valid and polygon.area > 0
        parts.append({'rings': rings})
    assert parts
    return parts


def polygon_for(parts):
    return unary_union([Polygon(p['rings'][0], p['rings'][1:]) for p in parts])


def mip_bytes(width, height):
    result = 0
    while True:
        result += width * height * 4
        if width == height == 1:
            return result
        width, height = max(1, width // 2), max(1, height // 2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    definitions = read(SOURCE / 'identities.json')['identities']
    source_manifest = read(SOURCE / 'sources.json')
    wanted_ids = {i for d in definitions for i in d['sourceBuildingIds']}
    wanted_annotations = {d['annotationId'] for d in definitions}
    features, annotations = {}, {}
    original = ET.Element(G + 'FeatureCollection')
    for source in source_manifest['sources']:
        for file in source['files']:
            path = REPORT / file['asset']
            assert hashlib.sha256(path.read_bytes()).hexdigest() == file['sha256']
            for member in ET.parse(path).getroot().findall(G + 'featureMember'):
                node = list(member)[0]
                pr = properties(node)
                if pr.get('BUILDINGID') in wanted_ids:
                    parts = source_parts(node)
                    features.setdefault(pr['BUILDINGID'], []).append({
                        'parts': parts, 'sourceProperties': pr, 'sheet': source['sheet'],
                        'sourceFile': file['asset'], 'sourceFileSha256': file['sha256'],
                    })
                    original.append(node)
                if pr.get('FeatureID') in wanted_annotations and 'TextString' in pr:
                    north, east = map(float, node.find('.//' + G + 'pos').text.split())
                    annotations.setdefault(pr['FeatureID'], []).append({
                        **pr, 'sheet': source['sheet'], 'localXZ': [east - 844800, 820500 - north],
                    })
                    original.append(node)
    projection_path = SOURCE / source_manifest['projectedSourceObjects']['asset']
    assert hashlib.sha256(projection_path.read_bytes()).hexdigest() == source_manifest['projectedSourceObjects']['sha256']
    source_objects = read(projection_path)
    existing_bundles = read(ROOT / 'public/models/exteriors/manifest.json')['bundles']
    installed_owners = {o['id']: 'building:' + b['buildingId'] for b in existing_bundles for o in b['objects']}
    installed_assets = {o['id']: '/models/exteriors/' + o['url'] for b in existing_bundles for o in b['objects']}
    baseline = read(ROOT / 'public/models/texture-detail-manifest.json')['tiles']
    rows, domains, aggregate_domains, object_owners = [], [], [], []
    for definition in definitions:
        annotation_candidates = annotations[definition['annotationId']]
        annotation = next((a for a in annotation_candidates if a['TextString'].isascii()), annotation_candidates[0])
        source_ids = definition['sourceBuildingIds']
        parts, fragments = [], []
        for source_id in source_ids:
            for fragment in features[source_id]:
                parts.extend(fragment['parts'])
                fragments.append(fragment)
        geometry = polygon_for(parts)
        assert geometry.is_valid and geometry.area > 0
        assert geometry.covers(Point(annotation['localXZ'])), definition['name']
        area_sum = sum(polygon_for(f['parts']).area for f in fragments)
        assert abs(area_sum - geometry.area) < 1e-5, 'Duplicated source fragments'
        base = min(float(f['sourceProperties']['BASELEVEL']) for f in fragments)
        roof = max(float(f['sourceProperties']['ROOFLEVEL']) for f in fragments)
        domain_id = 'physical-domain:ib1000:' + '+'.join(source_ids)
        domain = {
            'entityId': definition['entityId'], 'physicalDomainId': domain_id,
            'parts': parts, 'boundaryToleranceMeters': 0.15, 'minY': base, 'maxY': roof,
            'sourceBuildingId': source_ids[0], 'sourceBuildingIds': source_ids,
            'sourceFragments': fragments, 'annotation': annotation,
            'method': 'Named original BuildingAnno point contained in the original closed Building T polygon. Equal BUILDINGID sheet fragments retained together; no nearest-label or buffer assignment.',
            'completeAcrossSavedSheetEdges': True,
        }
        if definition.get('componentId'):
            domain['componentId'] = definition['componentId']
        if definition.get('sharedPhysicalEnvelopeWith'):
            domain['sharedPhysicalEnvelopeWith'] = definition['sharedPhysicalEnvelopeWith']
        (aggregate_domains if definition['action'] == 'aggregate-domain-audit-only' else domains).append(domain)
        matches = []
        for source_object in source_objects:
            projected = shape(source_object['sourceProjection'])
            intersection = geometry.intersection(projected).area
            if intersection / geometry.area < 0.1:
                continue
            matches.append({
                **{k: v for k, v in source_object.items() if k != 'sourceProjection'},
                'domainCoveredRatio': intersection / geometry.area,
                'sourceInsideDomainRatio': intersection / projected.area,
                'intersectionM2': intersection,
                'textureMipBytes': sum(mip_bytes(*wh) for wh in source_object['textureDimensions']),
                'currentlyInstalledOwner': installed_owners.get(source_object['id']),
                'currentlyInstalledAsset': installed_assets.get(source_object['id']),
                'nativeAttributeLinkMeaning': 'Same government model family ID prefix only; .att contains no human building name. Geometry/name association is independently established by official GML and original glTF projection.',
            })
        for source_id in definition.get('sourceObjectIds', []):
            match = next(m for m in matches if m['id'] == source_id)
            assert match['domainCoveredRatio'] > 0.96 and match['sourceInsideDomainRatio'] > 0.93
            object_owners.append({
                'sourceObjectId': source_id, 'entityId': definition['entityId'],
                'asset': installed_assets.get(source_id),
                'physicalDomainId': domain_id, 'currentBundleOwner': installed_owners.get(source_id),
                'domainCoveredRatio': match['domainCoveredRatio'],
                'sourceInsideDomainRatio': match['sourceInsideDomainRatio'],
                'interpretation': 'Exterior source object matches this named tower body. Existing University Center floor/room selection remains higher priority when opened. No C/D use-by-floor allocation was inferred.',
            })
        tile_matches = []
        texture_urls = {}
        for tile in baseline:
            b = tile['bounds']
            if geometry.intersection(box(b['min'][0], b['min'][2], b['max'][0], b['max'][2])).area <= 0:
                continue
            tile_matches.append(tile['id'])
            for texture in tile['materials'].values():
                texture_urls[texture['url']] = texture
        rows.append({
            **definition, 'physicalDomainId': domain_id, 'sourceAnnotation': annotation,
            'sourceFragments': [{'sheet': f['sheet'], 'buildingId': f['sourceProperties']['BUILDINGID'],
                                 'lastUpdateDate': f['sourceProperties']['LASTUPDATEDATE'],
                                 'areaM2': polygon_for(f['parts']).area} for f in fragments],
            'domainAreaM2': geometry.area, 'boundsXZ': list(geometry.bounds),
            'originalBaseLevel': base, 'originalRoofLevel': roof,
            'sourceObjectMatches': matches, 'baselineIdsIntersectingBounds': tile_matches,
            'baselineMappingMeaning': 'Actual closed domain intersects source tile bounds; scheduling/quality audit candidates only. This is not proof of whole-building triangle coverage or visual quality.',
            'baselineOriginalTextureCount': len(texture_urls),
            'baselineOriginalTextureMipBytes': sum(mip_bytes(t['width'], t['height']) for t in texture_urls.values()),
            'qualityStatus': 'pending-per-building-runtime-and-current-appearance-comparison',
        })
    # Cross-source models are disjoint. Original GML and model boundaries differ
    # slightly, so retain (and bound) the measured opposite-domain overlap.
    for owner in object_owners:
        source_object = next(s for s in source_objects if s['id'] == owner['sourceObjectId'])
        other = next(d for d in domains if d.get('sharedPhysicalEnvelopeWith') and d['entityId'] != owner['entityId'])
        overlap = shape(source_object['sourceProjection']).intersection(polygon_for(other['parts'])).area
        owner['otherTowerDomainIntersectionM2'] = overlap
        owner['otherTowerDomainIntersectionRatio'] = overlap / polygon_for(other['parts']).area
        other_owner = next(o for o in object_owners if o['entityId'] == other['entityId'])
        other_source = next(s for s in source_objects if s['id'] == other_owner['sourceObjectId'])
        owner['otherTowerModelIntersectionM2'] = shape(source_object['sourceProjection']).intersection(shape(other_source['sourceProjection'])).area
        assert owner['otherTowerDomainIntersectionRatio'] < 0.005, 'Material cross-tower domain assignment'
        assert owner['otherTowerModelIntersectionM2'] < 1e-8, 'Overlapping C/D source object ownership'
    write(PUBLIC / 'building-domains-extra.json', {
        'version': 1, 'domains': domains, 'auditOnlyAggregateDomains': aggregate_domains,
        'sourceObjectOwners': object_owners, 'sourceEvidence': '/data/picking/named-building-source-features-extra.gml',
        'coordinates': source_manifest['coordinateSystem'],
        'heightMeaning': 'Original iB1000 BASELEVEL/ROOFLEVEL are retained as metadata. No generated visual extrusion, invented floor allocation, or claimed glTF height-datum calibration.',
        'countingNote': 'Registry entity count is not a unique physical building count. C/D and University Center share exterior envelopes; Hall VI has two physical tower components under one entity. Aggregate numbered tower domains remain unsplit.',
    })
    ET.ElementTree(original).write(PUBLIC / 'named-building-source-features-extra.gml', encoding='utf-8', xml_declaration=True)
    registry_path = ROOT / 'public/data/entity-registry.json'
    registry = read(registry_path)
    by_id = {e['entityId']: e for e in registry['entities']}
    old_ids = set(by_id)
    old_legacy = dict(registry['legacyMap'])
    if args.apply:
        for definition in definitions:
            if definition['action'] == 'aggregate-domain-audit-only':
                continue
            entity_id = definition['entityId']
            if definition['action'] == 'new-building' and entity_id not in by_id:
                assert definition['name'] not in {e['name'] for e in by_id.values()}, 'Duplicate canonical name'
                entity = {
                    'entityId': entity_id, 'type': 'building', 'name': definition['name'],
                    'aliases': definition['aliases'], 'externalIds': {},
                    'parentId': definition['parentId'], 'representations': [], 'relations': [],
                    'sourceId': 'named-building-identity', 'status': 'existing',
                    'identityEvidence': '/data/picking/building-domains-extra.json',
                    'identityStatus': 'official named annotation inside complete source building domain; exterior visual quality not yet verified',
                }
                registry['entities'].append(entity)
                by_id[entity_id] = entity
                parent = by_id[definition['parentId']]
                relation = {'type': 'contains', 'targetId': entity_id}
                if relation not in parent['relations']:
                    parent['relations'].append(relation)
            entity = by_id[entity_id]
            domain = next(d for d in domains if d['entityId'] == entity_id and d['sourceBuildingIds'] == definition['sourceBuildingIds'])
            min_x, min_z, max_x, max_z = polygon_for(domain['parts']).bounds
            representation = {
                'id': 'rep:named-domain:' + definition['sourceBuildingIds'][0],
                'type': 'footprint', 'subtype': 'official_ib1000_named_building_domain',
                'asset': DOMAIN_ASSET, 'featureId': domain['physicalDomainId'],
                'bounds': {'min': [min_x, domain['minY'], min_z], 'max': [max_x, domain['maxY'], max_z]},
                'position': [domain['annotation']['localXZ'][0], domain['minY'], domain['annotation']['localXZ'][1]],
                'positionMethod': 'original-official-BuildingAnno-coordinate-inside-complete-source-domain',
                'heightMeaning': 'Display anchor Y uses the original iB1000 BASELEVEL metadata. It is not a measured entrance elevation, room floor, or calibrated glTF datum.',
                'sourceId': 'named-building-identity',
                'evidence': 'Original closed iB1000 boundary; map annotation is a reference point, not a surveyed entrance. Shared envelopes and model/geometry dates are recorded in the linked identity audit.',
            }
            entity['representations'] = [r for r in entity['representations'] if r['id'] != representation['id']] + [representation]
            assert len(representation['position']) == 3 and all(isinstance(v, (int, float)) and math.isfinite(v) for v in representation['position'])
            entity.setdefault('externalIds', {})['iB1000BuildingIds'] = sorted(set(entity.get('externalIds', {}).get('iB1000BuildingIds', []) + definition['sourceBuildingIds']))
            if definition.get('componentId'):
                components = entity.setdefault('physicalComponents', [])
                components[:] = [c for c in components if c['componentId'] != definition['componentId']]
                components.append({'componentId': definition['componentId'], 'name': definition['name'], 'physicalDomainId': domain['physicalDomainId'], 'sourceBuildingIds': definition['sourceBuildingIds']})
            if definition.get('sharedPhysicalEnvelopeWith'):
                other_id = definition['sharedPhysicalEnvelopeWith']
                for a, b in [(entity, other_id), (by_id[other_id], entity_id)]:
                    relation = {'type': 'sharedPhysicalEnvelopeWith', 'targetId': b,
                                'evidence': 'Official Tower C/D annotation domains overlap the existing University Center source exterior/floor drawing; no use-by-floor partition is established.'}
                    if not any(r['type'] == relation['type'] and r['targetId'] == b for r in a['relations']):
                        a['relations'].append(relation)
                by_id[other_id]['physicalCountingStatus'] = 'shared C/D envelopes; do not count as a third independent physical building'
        registry['sources']['named-building-identity'] = {
            'asset': DOMAIN_ASSET, 'url': MAP_URL,
            'note': 'Official campus naming cross-checked against original iB1000 BuildingAnno and Building rings, including equal-ID sheet fragments. No inferred apartment-unit buildings or per-tower subdivision of grouped blocks.',
        }
        registry['counts']['entities'] = len(registry['entities'])
        registry['counts']['byType'] = dict(Counter(e['type'] for e in registry['entities']))
        registry['counts']['representations'] = sum(len(e['representations']) for e in registry['entities'])
        registry['counts']['namedBuildingIdentityExtension'] = {
            'newBuildingEntities': 22, 'separatelyNamedApartmentBlockBodies': 4,
            'unsplitStaffTowerNames': 15, 'unsplitStaffTowerPhysicalDomains': 5,
            'hallVISourceTowerComponents': 2, 'uniquePhysicalBuildingTotal': None,
            'reason': 'Shared University Center/C/D envelopes, two Hall VI bodies, grouped staff towers and other existing unresolved domains prevent interpreting the registry count as the final physical denominator.',
        }
        assert set(by_id).issuperset(old_ids) and registry['legacyMap'] == old_legacy
        registry_path.write_text(json.dumps(registry, ensure_ascii=False, separators=(',', ':')) + '\n')
    assert len(by_id) == len(registry['entities'])
    report = {
        'status': 'identity-domain-evidence-verified; visual-quality-not-verified',
        'checkedAt': '2026-09-06', 'sourceSurveyDate': None,
        'counts': {'newBuildingEntitiesDefined': 22, 'runtimeDomains': len(domains),
                   'aggregateAuditDomains': len(aggregate_domains), 'sourceObjectOwnersVerified': len(object_owners),
                   'registryBuildings': sum(e['type'] == 'building' for e in registry['entities']),
                   'uniquePhysicalBuildingTotal': None},
        'rows': rows, 'sourceObjectOwners': object_owners,
        'pending': [
            'Staff Tower 5-19 identities are named components of five continuous official T domains; exact per-number division is not established.',
            'University Center floor/room use across Tower C/D is unpartitioned. Keep its stable ID, floors and shared exterior bundle; do not duplicate the two source objects.',
            'Distinguished Guest Lodge and UniLodge have no independent confirmed source domain in this audit; do not infer from a nearby President/Tower polygon.',
            'Original source geometry/texture dates, current-condition comparisons, complete facade coverage and close-distance visual quality remain per-building tasks.',
        ],
        'networkUsedByThisScript': False, 'registryApplied': args.apply,
    }
    write(REPORT / 'named-building-identities.json', report)
    inventory_path = REPORT / 'named-building-inventory.json'
    inventory = read(inventory_path)
    by_name = {r['name']: r for r in rows}
    seen_canonical = set()
    for row in inventory['rows']:
        matched = by_name.get(row['name'])
        if matched and matched['action'] == 'new-building':
            row['canonicalId'] = matched['entityId']
            row['physicalDomainIds'] = [matched['physicalDomainId']]
            row['inventoryStatus'] = 'canonical-building-added-official-named-domain-verified'
            row.setdefault('qualityStatus', matched['qualityStatus'])
        if row.get('canonicalId'):
            seen_canonical.add(row['canonicalId'])
            if row['canonicalId'] in by_id:
                row['representationCount'] = len(by_id[row['canonicalId']]['representations'])
            matched_domains = [r['physicalDomainId'] for r in rows if r['entityId'] == row['canonicalId']]
            if matched_domains:
                row['physicalDomainIds'] = matched_domains
        elif row['name'].startswith('Staff Quarters Tower '):
            aggregate = next((r for r in rows if row['name'] in r.get('namedComponents', [])), None)
            if aggregate:
                row['sharedGroupPhysicalDomainId'] = aggregate['physicalDomainId']
                row['inventoryStatus'] = 'named-component-in-verified-continuous-group-domain; individual-division-pending'
    for row in rows:
        if row['action'] == 'new-building' and row['entityId'] not in seen_canonical:
            inventory['rows'].append({
                'auditId': row['entityId'], 'canonicalId': row['entityId'], 'name': row['name'],
                'aliases': row['aliases'], 'physicalDomainIds': [row['physicalDomainId']],
                'inventoryStatus': 'canonical-building-added-official-named-domain-verified',
                'qualityStatus': row['qualityStatus'],
            })
            seen_canonical.add(row['entityId'])
    uc = next(r for r in inventory['rows'] if r.get('canonicalId') == 'building:b00000000000000000000006')
    uc['physicalDomainIds'] = [o['physicalDomainId'] for o in object_owners]
    uc['physicalCountingStatus'] = 'Shared C/D envelopes; not a third independent exterior body. Keep existing University Center entity and floors.'
    inventory['status'] = 'in-progress-physical-domains-expanded; visual-quality-not-complete'
    inventory['canonicalBuildings'] = report['counts']['registryBuildings']
    inventory['namedCandidatesCurrentlyHiddenInAggregateZones'] = 15
    inventory['originalNamedCandidatesInAggregateZones'] = 33
    inventory['uniquePhysicalBuildingTotal'] = None
    inventory['identityDomainAudit'] = 'named-building-identities.json'
    inventory['notes'] = [
        f"{report['counts']['registryBuildings']} registry building records are not the independently counted physical-building total.",
        '22 independently named source domains added: C/D, Staff1-4, House1-8, P-S, and four apartment ranges.',
        '15 numbered Staff Tower names remain unsplit in five continuous source T domains.',
        'University Center shares C/D envelopes; Hall VI retains one entity and two named source tower components.',
        'The final physical denominator stays open. Identity/domain validation is not a close-distance visual-quality pass.',
    ]
    for audit in inventory.get('additionalAudits', []):
        if audit['name'].startswith('UG Hall VI:'):
            audit['identityDomainStatus'] = 'Resolved two named T domains under existing hall; separate exterior visual QA remains pending.'
            audit['physicalDomainIds'] = [d['physicalDomainId'] for d in domains if d['entityId'] == 'building:6a85579974fe9a95803085ac']
        if audit['name'] == 'Staff Quarters Apartments 1–48':
            audit['identityDomainStatus'] = 'Resolved four named source block bodies for 1-12, 13-24, 25-36, 37-48; 48 unit addresses are not buildings.'
            audit['physicalDomainIds'] = [r['physicalDomainId'] for r in rows if r['name'].startswith('Staff Quarters Apartments ')]
    write(inventory_path, inventory)
    lines = ['# Named building identity and physical-domain audit', '',
             'Checked 2026-09-06. Identity evidence is verified; no row is a visual-quality pass. Registry building counts are not the final physical-building denominator.', '',
             '| Name | Registry owner | iB1000 physical domain | Original sheet fragments | Source model matches |',
             '|---|---|---|---|---|']
    for row in rows:
        fragments = ', '.join(f['sheet'] for f in row['sourceFragments'])
        models = ', '.join(m['id'] for m in row['sourceObjectMatches']) or 'No matching local individual source object established'
        lines.append(f"| {row['name']} | {row['entityId']} | {', '.join(row['sourceBuildingIds'])} | {fragments} | {models} |")
    lines += ['', '## Evidence boundaries', '',
              '- The 22 added records have independent official named T polygons. Four apartment ranges are four block bodies, not 48 buildings.',
              '- Staff Towers 5-19 remain 15 named candidates across five unpartitioned source domains. No nearest-label allocation or per-number artificial subdivision was made.',
              '- UG Hall VI keeps one hall identity with two named physical components. Its individual-source models include geometry outside the bare T domains; those overlaps are reported, not silently classified as another tower.',
              '- Tower C and D match the two source objects already loaded by the University Center bundle. The University Center ID, published floors and bundle remain intact. Shared-envelope relations prevent interpreting it as a third exterior body. Outside roof/wall picks can use the verified sourceObjectOwners table; published room/floor hits take precedence.',
              '- Matching source model family prefixes links saved native FBX .att records. The .att rows do not contain building names, and their original date columns are not assumed to be photography dates.',
              '- BASELEVEL/ROOFLEVEL are source metadata; no extra render geometry, floor allocation or height-datum correction was created. Original named point coordinates are reference points, not entrances.',
              '- Baseline tile intersections use original tile bounds and are audit/scheduling candidates. They do not prove complete triangle coverage or close-distance clarity.', '',
              '## Sources', '',
              '- [HKUST official August 2026 campus map](https://publish.ust.hk/univ/maps/Campus_Map_Color.pdf), saved as public/maps/campus-aug2026.pdf; metadata/export date is not a field survey date.',
              '- Original iB1000 Building and BuildingAnno GML from five bounded sheets; file hashes, source URLs and retrieval/revision distinctions are in identity-sources/sources.json. Cross-sheet bodies retain every same-ID original fragment.',
              '- [HKUST CDO Tower C/D remodeling](https://cdo.hkust.edu.hk/projects/remodeling-works-of-tower-c-and-tower-d): C completed in 2022, D in 2025. These completion dates are not dates of the government textures.',
              '- [CMO 2022R unit list](https://cmo.hkust.edu.hk/sites/default/files/2023-02/Reallocation_2022R-Units_List.pdf) separates Building and Unit columns; it corroborates tower identities and that apartment numbers are dwelling-unit addresses. This historical occupancy list does not certify current exterior condition.', '']
    (REPORT / 'named-building-identities.md').write_text('\n'.join(lines))
    print(json.dumps(report['counts'], ensure_ascii=False))


if __name__ == '__main__':
    main()
