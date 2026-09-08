#!/usr/bin/env python3
"""Build the verified public profile without changing full-local assets or previews."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    if not (ROOT / 'node_modules/.bin/vinext').is_file():
        raise ValueError('Install the locked dependencies with npm ci first.')
    spec = importlib.util.spec_from_file_location('data_package', ROOT / 'scripts/data-package.py')
    data = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(data)
    catalog = json.loads((ROOT / 'assets/government-baseline-v1.json').read_text())
    archive = ROOT / '.local/government-baseline-v1.zip'
    archive.parent.mkdir(exist_ok=True)
    if not archive.exists():
        request = urllib.request.Request(catalog['archive']['url'], headers={'User-Agent': 'HKUSTsandbox-Sites/1'})
        partial = archive.with_suffix('.zip.part')
        with urllib.request.urlopen(request, timeout=120) as src, partial.open('wb') as dst:
            shutil.copyfileobj(src, dst)
        if partial.stat().st_size != catalog['archive']['bytes'] or data.digest(partial) != catalog['archive']['sha256']:
            raise ValueError('Downloaded public data checksum mismatch.')
        partial.replace(archive)
    if archive.stat().st_size != catalog['archive']['bytes'] or data.digest(archive) != catalog['archive']['sha256']:
        raise ValueError('Public data checksum mismatch; no build was performed.')

    # This disposable build directory is not a second maintained checkout.
    with tempfile.TemporaryDirectory(prefix='sites-build-', dir=ROOT / '.local') as temp:
        stage = Path(temp)
        names = subprocess.check_output(
            ['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=ROOT,
        ).decode().split('\0')
        for name in sorted(set(names)):
            if not name or name.startswith('public/'):
                continue
            source = ROOT / name
            if source.is_symlink():
                raise ValueError('Source symlink is not supported: ' + name)
            if not source.is_file():
                continue
            target = stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        data.ROOT = stage
        data.install(archive)
        profile = json.loads((stage / 'public/data/dataset-profile.json').read_text())
        if profile['id'] != 'government-baseline':
            raise ValueError('Sites publication must use the verified government-baseline profile.')
        (stage / 'node_modules').symlink_to(ROOT / 'node_modules', target_is_directory=True)
        subprocess.run(['npm', 'run', 'check'], cwd=stage, check=True)
        subprocess.run(['npm', 'run', 'build'], cwd=stage, check=True)
        output = stage / 'dist/client'
        if not (output / 'index.html').is_file():
            raise ValueError('Static index.html was not emitted.')
        # Require byte-identical installed data in the published output.
        data.verify(output)
        if json.loads((output / 'data/dataset-profile.json').read_text())['id'] != profile['id']:
            raise ValueError('Published data profile mismatch.')
        if any((output / name).exists() for name in ['brand', 'photos', 'maps']):
            raise ValueError('Local-only image directory leaked into public build.')
        previous = ROOT / '.local/sites-out-previous'
        if previous.exists():
            shutil.rmtree(previous)
        destination = ROOT / 'out'
        if destination.is_symlink():
            raise ValueError('Refusing to replace a linked output directory.')
        if destination.exists():
            destination.rename(previous)
        output.rename(destination)
        files = [p for p in destination.rglob('*') if p.is_file()]
        print(json.dumps({'profile': profile['id'], 'files': len(files), 'bytes': sum(p.stat().st_size for p in files),
                          'largestFileBytes': max(p.stat().st_size for p in files), 'output': str(destination)}))
    print('Sites build ready. public/, dist/ and .preview/ were preserved.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error))
