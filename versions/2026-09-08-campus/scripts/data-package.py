#!/usr/bin/env python3
"""Install verified runtime data, or export an owner's local data without publishing it."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def safe_name(name):
    p = PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or '\\' in name or not p.parts:
        raise ValueError('Unsafe package path: ' + name)
    return p


def verify(root):
    manifest = json.loads((root / 'SHA256SUMS.json').read_text())
    for name, info in manifest['files'].items():
        p = root / safe_name(name)
        if p.is_symlink() or not p.is_file():
            raise ValueError('Missing or linked data: ' + name)
        if p.stat().st_size != info['bytes'] or digest(p) != info['sha256']:
            raise ValueError('Data checksum mismatch: ' + name)
    print('Verified', len(manifest['files']), 'files; profile', manifest['profile'])
    return manifest


def install(archive):
    public = ROOT / 'public'
    if (public / 'data/entity-registry.json').exists():
        raise ValueError('Runtime data already installed. Use a separate clone; existing full-local data is not overwritten.')
    local = ROOT / '.local';local.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='data-import-', dir=local) as temp:
        stage = Path(temp)
        with zipfile.ZipFile(archive) as z:
            names = z.namelist()
            if len(names) != len(set(names)):
                raise ValueError('Duplicate ZIP member')
            inventory = json.loads(z.read('public/SHA256SUMS.json'))
            allowed = {'public/' + str(safe_name(n)) for n in inventory['files']}
            allowed.add('public/SHA256SUMS.json')
            if set(names) != allowed:
                raise ValueError('ZIP contains unlisted or missing files')
            for info in z.infolist():
                p = safe_name(info.filename)
                if p.parts[0] != 'public' or stat.S_ISLNK(info.external_attr >> 16):
                    raise ValueError('ZIP contains linked or external data')
                target = stage / p
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(info) as src, target.open('wb') as dst:
                    shutil.copyfileobj(src, dst)
        verify(stage / 'public')
        # Do not overwrite authored tools shipped in the Git tree.
        for p in (stage / 'public').rglob('*'):
            target = public / p.relative_to(stage / 'public')
            if p.is_file() and target.exists() and digest(p) != digest(target):
                raise ValueError('Existing file differs: ' + str(target.relative_to(ROOT)))
        shutil.copytree(stage / 'public', public, dirs_exist_ok=True)
    print('Installed data. Rebuild the application before previewing this profile.')


def fetch():
    catalog = json.loads((ROOT / 'assets/government-baseline-v1.json').read_text())
    download = catalog['archive']
    local = ROOT / '.local/downloads';local.mkdir(parents=True, exist_ok=True)
    archive = local / Path(download['url']).name
    if not archive.exists():
        partial = archive.with_suffix(archive.suffix + '.part')
        request = urllib.request.Request(download['url'], headers={'User-Agent': 'HKUSTsandbox-data-installer/1'})
        with urllib.request.urlopen(request, timeout=120) as src, partial.open('wb') as dst:
            shutil.copyfileobj(src, dst)
        if partial.stat().st_size != download['bytes'] or digest(partial) != download['sha256']:
            raise ValueError('Downloaded archive checksum mismatch; partial file retained for inspection.')
        partial.replace(archive)
    if archive.stat().st_size != download['bytes'] or digest(archive) != download['sha256']:
        raise ValueError('Cached archive checksum mismatch')
    install(archive)


def export_local(destination):
    public = ROOT / 'public'
    if destination.exists():
        raise ValueError('Export destination already exists')
    profile = json.loads((public / 'data/dataset-profile.json').read_text())['id']
    files = sorted(p for p in public.rglob('*') if p.is_file() and p.name != 'SHA256SUMS.json' and '__pycache__' not in p.parts)
    if any(p.is_symlink() for p in files):
        raise ValueError('Export refuses symlinked assets')
    inventory = {'version': 1, 'profile': profile, 'files': {str(p.relative_to(public)): {'bytes': p.stat().st_size, 'sha256': digest(p)} for p in files}}
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=1, allowZip64=True) as z:
        for p in files:
            z.write(p, 'public/' + str(p.relative_to(public)))
        z.writestr('public/SHA256SUMS.json', json.dumps(inventory, ensure_ascii=False, indent=2))
    print('Exported', len(files), 'files to', destination)
    print('SHA-256:', digest(destination))
    if profile == 'full-local':
        print('LOCAL TRANSFER ONLY: this package includes third-party assets not cleared for public redistribution.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('fetch')
    sub.add_parser('verify')
    sub.add_parser('install').add_argument('archive', type=Path)
    sub.add_parser('export-local').add_argument('archive', type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'fetch': fetch()
        elif args.command == 'verify': verify(ROOT / 'public')
        elif args.command == 'install': install(args.archive)
        else: export_local(args.archive)
    except (ValueError, OSError, KeyError, zipfile.BadZipFile) as error:
        parser.exit(1, str(error) + '\n')
