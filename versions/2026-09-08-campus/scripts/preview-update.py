#!/usr/bin/env python3
"""Build away from the served snapshot, then atomically switch the local preview."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--existing-build', action='store_true')
args = parser.parse_args()
if not args.existing_build:
    subprocess.run(['npm', 'run', 'check'], cwd=root, check=True)
    subprocess.run(['npm', 'run', 'build'], cwd=root, check=True)
source = root / 'dist/client'
if not (source / 'index.html').is_file():
    raise SystemExit('No completed static build found')
base = root / '.preview'
base.mkdir(exist_ok=True)
name = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
release = base / name
if sys.platform == 'darwin':
    subprocess.run(['cp', '-cR', str(source), str(release)], check=True)
else:
    shutil.copytree(source, release)
# Keep prior hashed code assets usable for tabs that were already open.
current = base / 'current'
if current.exists():
    for asset_root in ['assets', '_next/static']:
        old_assets = current / asset_root
        if old_assets.exists():
            for old in old_assets.rglob('*'):
                target = release / asset_root / old.relative_to(old_assets)
                if old.is_file() and not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(old, target)
link = base / ('next-' + name)
link.symlink_to(release.name, target_is_directory=True)
os.replace(link, current)
print('Local preview updated: http://127.0.0.1:4317/')
print('Snapshot:', release)
