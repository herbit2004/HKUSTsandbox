#!/usr/bin/env python3
"""Build an isolated Sites artifact, preserving local assets and the 4317 preview."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import mimetypes
from pathlib import Path
import shutil
import subprocess
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
STATIC_LIMIT = 25 * 1024 * 1024
SEGMENT_SIZE = 16 * 1024 * 1024


def runtime_files(directory):
    return sorted(p for p in directory.rglob('*') if p.is_file()
                  and p.name != '.DS_Store' and not p.name.startswith('._') and '__pycache__' not in p.parts)


def main(profile):
    if not (ROOT / 'node_modules/.bin/vinext').is_file():
        raise ValueError('Install the locked dependencies with npm ci first.')
    spec = importlib.util.spec_from_file_location('data_package', ROOT / 'scripts/data-package.py')
    data = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(data)
    local = ROOT / '.local'
    local.mkdir(exist_ok=True)
    archive = local / 'government-baseline-v1.zip'
    if profile == 'government-baseline':
        catalog = json.loads((ROOT / 'assets/government-baseline-v1.json').read_text())
        if not archive.exists():
            request = urllib.request.Request(catalog['archive']['url'], headers={'User-Agent': 'HKUSTsandbox-Sites/2'})
            partial = archive.with_suffix('.zip.part')
            with urllib.request.urlopen(request, timeout=120) as src, partial.open('wb') as dst:
                shutil.copyfileobj(src, dst)
            if partial.stat().st_size != catalog['archive']['bytes'] or data.digest(partial) != catalog['archive']['sha256']:
                raise ValueError('Downloaded public data checksum mismatch.')
            partial.replace(archive)
        if archive.stat().st_size != catalog['archive']['bytes'] or data.digest(archive) != catalog['archive']['sha256']:
            raise ValueError('Public data checksum mismatch.')
    elif json.loads((ROOT / 'public/data/dataset-profile.json').read_text())['id'] != 'full-local':
        raise ValueError('Full-local data is not installed. Use --profile government-baseline for the public subset.')

    # A disposable build directory, not another maintained source checkout.
    with tempfile.TemporaryDirectory(prefix='sites-build-', dir=local) as temp:
        stage = Path(temp)
        names = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=ROOT).decode().split('\0')
        for name in sorted(set(names)):
            if not name or name.startswith('public/'):
                continue
            source = ROOT / name
            if source.is_symlink():
                raise ValueError('Source symlink is not supported: ' + name)
            if source.is_file():
                target = stage / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        if profile == 'government-baseline':
            data.ROOT = stage
            data.install(archive)
        else:
            for source in runtime_files(ROOT / 'public'):
                if source.is_symlink():
                    raise ValueError('Linked runtime resource: ' + str(source))
                target = stage / 'public' / source.relative_to(ROOT / 'public')
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        inventory = {str(p.relative_to(stage / 'public')): {'bytes': p.stat().st_size, 'sha256': data.digest(p)}
                     for p in runtime_files(stage / 'public')}
        (stage / 'node_modules').symlink_to(ROOT / 'node_modules', target_is_directory=True)
        subprocess.run(['npm', 'run', 'check'], cwd=stage, check=True)
        subprocess.run(['npm', 'run', 'build'], cwd=stage, check=True)
        client = stage / 'dist/client'
        if not (client / 'index.html').is_file():
            raise ValueError('Static index.html was not emitted.')
        for name, info in inventory.items():
            output = client / name
            if not output.is_file() or output.stat().st_size != info['bytes'] or data.digest(output) != info['sha256']:
                raise ValueError('Runtime data changed during build: ' + name)
        if json.loads((client / 'data/dataset-profile.json').read_text())['id'] != profile:
            raise ValueError('Published data profile mismatch.')
        if profile == 'government-baseline' and any((client / name).exists() for name in ['brand', 'photos', 'maps']):
            raise ValueError('Local-only images leaked into the public profile.')

        # Preserve the original URL and bytes via the Worker; no mesh/texture recompression.
        large = {}
        for output in runtime_files(client):
            if output.stat().st_size <= STATIC_LIMIT:
                continue
            name = str(output.relative_to(client))
            sha = data.digest(output)
            entry = {'bytes': output.stat().st_size, 'sha256': sha,
                     'contentType': 'model/gltf-binary' if output.suffix == '.glb' else mimetypes.guess_type(name)[0] or 'application/octet-stream',
                     'parts': []}
            joined_hash = hashlib.sha256()
            with output.open('rb') as source:
                while block := source.read(SEGMENT_SIZE):
                    part_name = f'_sites/segments/{sha}-{len(entry["parts"]):03}.bin'
                    part = client / part_name
                    part.parent.mkdir(parents=True, exist_ok=True)
                    part.write_bytes(block)
                    joined_hash.update(part.read_bytes())
                    entry['parts'].append({'url': '/' + part_name, 'bytes': len(block)})
            if joined_hash.hexdigest() != sha:
                raise ValueError('Segment byte verification failed: ' + name)
            large['/' + name] = entry
            output.unlink()
        metadata = client / '_sites'
        metadata.mkdir(exist_ok=True)
        (metadata / 'large-assets.json').write_text(json.dumps(large) + '\n')
        (metadata / 'runtime-integrity.json').write_text(json.dumps({'profile': profile, 'files': inventory}) + '\n')
        subprocess.run(['npx', '--no-install', 'vite', 'build', '--config', 'scripts/sites-worker.vite.mjs'], cwd=stage, check=True)
        if not (stage / 'dist/server/index.js').is_file():
            raise ValueError('Worker entrypoint was not emitted.')
        # The packaging helper consumes this artifact stage; source Git stays at ROOT.
        publication = stage / 'publication'
        publication.mkdir()
        (stage / 'dist').rename(publication / 'dist')
        (publication / '.openai').mkdir()
        shutil.copy2(ROOT / '.openai/hosting.json', publication / '.openai/hosting.json')
        previous = local / 'sites-out-previous'
        if previous.exists():
            shutil.rmtree(previous)
        destination = ROOT / 'out'
        if destination.is_symlink():
            raise ValueError('Refusing to replace a linked output directory.')
        if destination.exists():
            destination.rename(previous)
        publication.rename(destination)
        files = runtime_files(destination / 'dist/client')
        report = {'profile': profile, 'runtimeFiles': len(inventory), 'runtimeBytes': sum(v['bytes'] for v in inventory.values()),
                  'staticFiles': len(files), 'staticBytes': sum(p.stat().st_size for p in files),
                  'largestStaticFileBytes': max(p.stat().st_size for p in files), 'streamedAssets': large,
                  'packageRoot': str(destination)}
        (local / 'sites-build-validation.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps({k: v for k, v in report.items() if k != 'streamedAssets'}))
    print('Sites build ready. Local public/, dist/ and .preview/ were preserved.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=['full-local', 'government-baseline'], default='full-local')
    args = parser.parse_args()
    try:
        main(args.profile)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error))
