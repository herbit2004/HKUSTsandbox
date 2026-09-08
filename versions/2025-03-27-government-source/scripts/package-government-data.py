#!/usr/bin/env python3
"""Build the bounded government-baseline public dataset with Python stdlib only.

Does not edit the source project, infer buildings, fetch data, or publish anything.
Output is the CONTENTS of a public/ directory; it must not already exist.
Optional --archive contains public/... entries suitable for a versioned release.
Source data rights remain with the Hong Kong SAR Government under CSDI terms.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import struct
import tempfile
import zipfile

TERMS = 'https://portal.csdi.gov.hk/csdi-webpage/doc/TNC'
MESH_METADATA = 'https://portal.csdi.gov.hk/csdi-webpage/metadata/landsd_rcd_1671677054006_62261/html'
TERRAIN_METADATA = 'https://portal.csdi.gov.hk/csdi-webpage/metadata/cedd_rcd_1629267205233_87895/html'
PROFILE = {
    'version': 1, 'id': 'government-baseline',
    'enhancements': False, 'branding': False, 'campusMap': False,
    'title': 'HKUST Clear Water Bay — government terrain and photogrammetry baseline',
    'description': '292 existing government photogrammetry tiles and CEDD terrain. No named-building registry, indoor plans, campus photographs, university emblem, or current-form reconstructions are included.',
    'qualityStatus': 'Source-era baseline only; no building is certified as passing the full-campus Academic comparison standard.',
    'attributionUrl': '/DATASET.md',
    'terms': TERMS,
}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(root: Path, relative: str, value):
    destination = root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def safe_source(public: Path, relative: str) -> Path:
    name = PurePosixPath(relative)
    if name.is_absolute() or '..' in name.parts or '\\' in relative:
        raise ValueError('Unsafe source path: ' + relative)
    result = public.joinpath(*name.parts)
    if not result.is_file() or result.is_symlink() or not result.resolve().is_relative_to(public):
        raise ValueError('Missing, linked, or external source: ' + relative)
    return result


def check_glb(path: Path):
    """Require a self-contained GLB; never accidentally expose external attachments."""
    with path.open('rb') as f:
        header = f.read(12)
        if len(header) != 12:
            raise ValueError('Truncated GLB: ' + path.name)
        magic, version, length = struct.unpack('<4sII', header)
        if magic != b'glTF' or version != 2 or length != path.stat().st_size:
            raise ValueError('Invalid GLB header: ' + path.name)
        chunk_length, chunk_type = struct.unpack('<II', f.read(8))
        if chunk_type != 0x4E4F534A:
            raise ValueError('Missing GLB JSON: ' + path.name)
        data = json.loads(f.read(chunk_length).decode('utf-8').rstrip(' \t\r\n\0'))
        for kind in ('buffers', 'images'):
            for item in data.get(kind, []):
                if 'uri' in item and not item['uri'].startswith('data:'):
                    raise ValueError('External GLB dependency: ' + path.name)


def embedded_image_signatures(path: Path):
    raw = path.read_bytes()
    json_length, _ = struct.unpack_from('<II', raw, 12)
    document = json.loads(raw[20:20 + json_length].decode('utf-8').rstrip(' \t\r\n\0'))
    binary_start = 20 + json_length + 8
    signatures = []
    for image in document.get('images', []):
        if 'uri' in image:
            signatures.append(hashlib.sha256(image['uri'].encode()).hexdigest())
        else:
            view = document['bufferViews'][image['bufferView']]
            start = binary_start + view.get('byteOffset', 0)
            signatures.append(hashlib.sha256(raw[start:start + view['byteLength']]).hexdigest())
    return signatures


def copy_checked(public: Path, stage: Path, relative: str, evidence: dict | None = None):
    source = safe_source(public, relative)
    sha = digest(source)
    if evidence is not None:
        if evidence.get('sha256') != sha or evidence.get('bytes') != source.stat().st_size:
            raise ValueError('Source no longer matches recorded SHA-256/size: ' + relative)
    if source.suffix == '.glb':
        check_glb(source)
    dest = stage / relative
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, dest)
    if digest(dest) != sha:
        raise ValueError('Copy verification failed: ' + relative)


def build(project: Path, output: Path):
    public = (project / 'public').resolve(strict=True)
    if output.exists() or output.is_symlink():
        raise ValueError('Output already exists; choose a new staging path (no overwrite): ' + str(output))
    if output.is_relative_to(public) or public.is_relative_to(output):
        raise ValueError('Output cannot overlap source public directory')
    mesh = read_json(safe_source(public, 'models/preview-manifest.json'))
    terrain = read_json(safe_source(public, 'terrain/terrain-manifest.json'))
    if mesh.get('source', {}).get('metadata') != MESH_METADATA or mesh['source'].get('terms') != TERMS:
        raise ValueError('Unexpected mesh source/terms; review provenance before packaging')
    if terrain.get('source_metadata') != TERRAIN_METADATA or terrain.get('terms') != TERMS:
        raise ValueError('Unexpected terrain source/terms; review provenance before packaging')
    tiles = mesh.get('tiles', [])
    if len(tiles) != 292 or len({t['url'] for t in tiles}) != 292:
        raise ValueError('Expected the existing complete 292-tile baseline; review changed source')
    for tile in tiles:
        if tile['url'].startswith('preview-glb/') and tile['url'].endswith('.glb'):
            continue
        correction = tile.get('sourceCorrection', {})
        if (not tile['url'].startswith('source-corrections/') or
            not tile['url'].endswith('.glb') or
            not correction.get('uncorrectedPreviewUrl', '').startswith('preview-glb/') or
            not correction.get('removedSourceTriangleIndices')):
            raise ValueError('Unexpected baseline asset path')
        original = safe_source(public, 'models/' + correction['uncorrectedPreviewUrl'])
        current = safe_source(public, 'models/' + tile['url'])
        if digest(original) != correction['uncorrectedPreviewSha256']:
            raise ValueError('Correction parent SHA-256 mismatch')
        if embedded_image_signatures(original) != embedded_image_signatures(current):
            raise ValueError('Correction changes photographic textures; requires source review')
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.' + output.name + '-stage-', dir=output.parent))
    try:
        for tile in tiles:
            copy_checked(public, stage, 'models/' + tile['url'], tile)
        mesh['distribution'] = {
            'profile': PROFILE['id'],
            'currentSourceCorrectionsRetained': sum('sourceCorrection' in tile for tile in tiles),
            'note': 'Current manifest URLs and SHA-256 are preserved, including source-triangle removals. Original GLB/3D Tiles and correction evidence attachments referenced as provenance are not distributed. No university photo or new reconstructed geometry is included.'
        }
        write_json(stage, 'models/preview-manifest.json', mesh)
        for name in ['terrain.glb', 'height-grid-5m.json']:
            copy_checked(public, stage, 'terrain/' + name, terrain['assets'][name])
        # Preserve original government source/processing metadata, but explicitly
        # distinguish the distributed subset from assets retained only locally.
        terrain['distribution'] = {
            'profile': PROFILE['id'],
            'includedRuntimeAssets': ['terrain.glb', 'height-grid-5m.json'],
            'otherAssets': 'Other files listed in the original assets record are provenance only and are not included in this baseline distribution.',
        }
        write_json(stage, 'terrain/terrain-manifest.json', terrain)
        coverage = read_json(safe_source(public, 'terrain/coverage/manifest.json'))
        if (coverage.get('tileCount') != 292 or
            coverage.get('source') != 'Lands Department 3D Visualisation Map original GLB + existing verified local transforms' or
            coverage.get('url') != 'photography-coverage-1m.png'):
            raise ValueError('Unexpected terrain coverage source')
        copy_checked(public, stage, 'terrain/coverage/manifest.json')
        copy_checked(public, stage, 'terrain/coverage/photography-coverage-1m.png')
        write_json(stage, 'data/dataset-profile.json', PROFILE)
        empty_note = 'Intentionally empty in government-baseline. See /DATASET.md; not evidence that the full local dataset is complete.'
        descriptors = {
            'data/entity-registry.json': {'version': 1, 'datasetProfile': PROFILE['id'], 'entities': [], 'legacyMap': {}, 'sources': {'mesh': {'url': MESH_METADATA}, 'terrain': {'url': TERRAIN_METADATA}}, 'notes': [empty_note]},
            'data/entity-resources.json': {'resources': []},
            'data/entity-registry-pois.json': [],
            'data/building-footprints.json': {'version': 1, 'footprints': []},
            'data/outdoor-entities.json': {'surfaces': [], 'roads': [], 'surfaceNodeEntityMap': {}},
            'data/panoramas.json': {'nodes': [], 'edges': []},
            'data/panoramas-online.json': {'nodes': [], 'edges': []},
            'interiors/manifest.json': {'version': 2, 'floors': []},
            'interiors/room-index.json': {'rooms': []},
            'models/texture-detail-manifest.json': {'version': 1, 'tiles': []},
            'models/hires/manifest.json': {'version': 1, 'patches': []},
            'models/exteriors/manifest.json': {'version': 1, 'bundles': []},
            'models/exteriors/baseline-texture-regions.json': {'version': 1, 'regions': []},
            'terrain/detail/manifest.json': {'version': 1, 'tiles': []},
            # Existing app compile-time JSON imports; all are inert schemas.
            'models/hires/road-protection.json': {'version': 1, 'clusters': []},
            'data/picking/building-domains.json': {'version': 1, 'domains': []},
            'data/picking/building-domains-extra.json': {'version': 1, 'domains': [], 'auditOnlyAggregateDomains': [], 'sourceObjectOwners': []},
            'surfaces/entrance/entity-picking-domains.json': {'version': 1, 'groundSurfaces': [], 'sourceAssociations': []},
            'models/current-forms/ivillage-rebuild/source-protection.json': {'disabled': True, 'url': '', 'sha256': '', 'bytes': 0, 'width': 1, 'height': 1, 'boundsXZ': {'min': [0, 0], 'max': [1, 1]}, 'groundBandMeters': 0, 'note': 'Inert schema for compilation; this profile must not call current-form loaders.'},
        }
        for name, descriptor in descriptors.items():
            if isinstance(descriptor, dict):
                descriptor['datasetNote'] = empty_note
            write_json(stage, name, descriptor)
        text = '''# Government baseline dataset\n\nThis is a real, bounded government terrain and photogrammetry subset for the same HKUSTsandbox application. It is not the complete local campus reconstruction. It contains 292 existing Lands Department photographic mesh tiles plus CEDD terrain and its height grid. Named-building selection, indoor floor plans, campus photos, panorama photos, university emblems, and photograph-derived current-form reconstructions are excluded. Empty optional manifests intentionally disable those datasets; no invented replacement buildings are supplied.\n\n## Attribution and terms\n\n- 3D Visualisation Map from Lands Department, Hong Kong SAR Government. Original data intellectual property belongs to the Government. [Metadata](https://portal.csdi.gov.hk/csdi-webpage/metadata/landsd_rcd_1671677054006_62261/html).\n- Civil Engineering and Development Department, Hong Kong SAR Government: display mesh derived from the public 0.5 m Digital Terrain Model. [Metadata](https://portal.csdi.gov.hk/csdi-webpage/metadata/cedd_rcd_1629267205233_87895/html).\n- Both government datasets remain subject to [CSDI terms](https://portal.csdi.gov.hk/csdi-webpage/doc/TNC). The repository's code license does not relicense these data or establish Government endorsement.\n\n## Processing, dates, and limitations\n\nThe existing source geometry is retained, including the three current manifest patches that remove isolated source triangles (see sourceCorrection per tile). Corrected tile photographic textures are verified byte-for-byte against their original previews; no reconstructed buildings are introduced. The existing preview textures were reduced to a maximum side of 512 pixels (JPEG quality 85). Per-tile affine placement and exact source/preview SHA-256 records are in models/preview-manifest.json. Its source package revision is 2025-03-27; capture date is not established. Revision is not capture date. The 2019-12-20 to 2020-02-02 terrain was sampled at 5 m from the 0.5 m CEDD raster with its original missing-data mask; terrain colors illustrate height and are not current aerial photography. See terrain/terrain-manifest.json for original acquisition URLs, processing, coordinate-system and vertical-datum limits. Original ZIP/TIFF/3D Tiles data and non-runtime exports referred to by the provenance manifests are not included in this distribution.\n\nBuildings and construction visible in the photographic source may be historical. This profile has no current-building quality approvals. It does not satisfy or replace the project's full-campus, per-building Academic comparison and multi-angle evidence requirements.\n\n## Installation and verification\n\nExtract this package at the repository root so its public/ files occupy the app's public/ directory. The app must use data/dataset-profile.json at build time: government-baseline disables optional university/current-form loaders and campus branding; rebuild after switching datasets. Verify every distributed file against SHA256SUMS.json. The app, this dataset, and compiled static output can then be hosted from an HTTP origin root without external runtime asset downloads. The archive contains only public/ files and can be kept for offline installation.\n\nThe packager uses an explicit allowlist, validates every GLB's recorded size and SHA-256 and checks for external GLB dependencies. It does not scan or publish the full local asset folders.\n'''
        (stage / 'DATASET.md').write_text(text, encoding='utf-8')
        files = {p.relative_to(stage).as_posix(): {'bytes': p.stat().st_size, 'sha256': digest(p)}
                 for p in sorted(stage.rglob('*')) if p.is_file()}
        inventory = {'version': 1, 'profile': PROFILE['id'], 'fileCount': len(files),
                     'totalBytes': sum(v['bytes'] for v in files.values()), 'files': files,
                     'scope': 'All distributed files except this inventory itself; paths relative to public/.'}
        write_json(stage, 'SHA256SUMS.json', inventory)
        os.rename(stage, output)
        return inventory
    except BaseException:
        shutil.rmtree(stage)
        raise


def make_archive(output: Path, archive: Path):
    if archive.exists() or archive.is_symlink():
        raise ValueError('Archive already exists (no overwrite): ' + str(archive))
    if archive.is_relative_to(output):
        raise ValueError('Archive cannot be inside the dataset directory')
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for path in sorted(output.rglob('*')):
            if path.is_file():
                info = zipfile.ZipInfo('public/' + path.relative_to(output).as_posix(), date_time=(2026, 9, 8, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                z.writestr(info, path.read_bytes(), compresslevel=6)
    with zipfile.ZipFile(archive) as z:
        bad = z.testzip()
        if bad:
            raise ValueError('Archive CRC failure: ' + bad)
    return {'bytes': archive.stat().st_size, 'sha256': digest(archive)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True, help='Existing full project, read only')
    parser.add_argument('--output', type=Path, required=True, help='New output directory containing public/ contents; cannot already exist')
    parser.add_argument('--archive', type=Path, help='Optional new deterministic ZIP with public/... paths')
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    inventory = build(args.project.expanduser().resolve(strict=True), output)
    summary = {'profile': PROFILE['id'], 'output': str(output), 'files': inventory['fileCount'] + 1,
               'runtimeTileCount': 292, 'bytesWithoutInventory': inventory['totalBytes']}
    if args.archive:
        archive = args.archive.expanduser().resolve()
        summary['archive'] = {'path': str(archive), **make_archive(output, archive)}
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
