#!/usr/bin/env python3
"""Apply one documented current-form roof material family to explicit roof/terrace primitives.

The source mesh positions, normals, colours, indices and existing embedded
images stay unchanged. UVs are new display coordinates in world X/Z metres.
The swatch is appearance evidence only; it does not claim the target roof has
the same measured finish or reconstruct any roof equipment.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('glb_io', ROOT/'scripts/bake-structure-shadows.py')
io = importlib.util.module_from_spec(spec); spec.loader.exec_module(io)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def pack(gltf, binary):
    gltf['buffers'] = [{'byteLength': len(binary)}]
    encoded = json.dumps(gltf, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
    encoded += b' ' * (-len(encoded) % 4)
    binary = bytes(binary) + b'\0' * (-len(binary) % 4)
    return (struct.pack('<4sII', b'glTF', 2, 28+len(encoded)+len(binary)) +
            struct.pack('<I4s', len(encoded), b'JSON') + encoded +
            struct.pack('<I4s', len(binary), b'BIN\0') + binary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('swatch', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--material', type=int, required=True)
    parser.add_argument('--repeat-metres', type=float, default=6)
    parser.add_argument('--source-url', required=True)
    args = parser.parse_args()
    if not np.isfinite(args.repeat_metres) or args.repeat_metres <= 0:
        raise ValueError('repeat-metres must be positive and finite')
    output = args.output.resolve()
    if output == args.source.resolve() or output.is_relative_to(ROOT/'public'):
        raise ValueError('Require isolated output distinct from source and outside public')

    gltf, source_binary, source_sha = io.read_glb(args.source)
    if args.material < 0 or args.material >= len(gltf.get('materials', [])):
        raise ValueError('Material index out of range')
    swatch = args.swatch.read_bytes()
    with Image.open(args.swatch) as image:
        if image.format != 'PNG':
            raise ValueError('Documented roof swatch must be PNG')
        dimensions = [image.width, image.height]
    before_images = io.image_hashes(gltf, source_binary)
    binary = bytearray(source_binary[:gltf['buffers'][0]['byteLength']])

    def view(payload, target=None):
        binary.extend(b'\0' * (-len(binary) % 4)); offset = len(binary); binary.extend(payload)
        record = {'buffer': 0, 'byteOffset': offset, 'byteLength': len(payload)}
        if target is not None:
            record['target'] = target
        gltf.setdefault('bufferViews', []).append(record)
        return len(gltf['bufferViews'])-1

    swatch_view = view(swatch)
    gltf.setdefault('images', []).append({'bufferView': swatch_view, 'mimeType': 'image/png',
        'name': 'shared-current-form-roof-paving-swatch'})
    image_i = len(gltf['images'])-1
    gltf.setdefault('samplers', []).append({'magFilter': 9729, 'minFilter': 9987,
        'wrapS': 10497, 'wrapT': 10497})
    sampler_i = len(gltf['samplers'])-1
    gltf.setdefault('textures', []).append({'source': image_i, 'sampler': sampler_i})
    texture_i = len(gltf['textures'])-1

    material = gltf['materials'][args.material]
    material.setdefault('pbrMetallicRoughness', {})['baseColorTexture'] = {'index': texture_i, 'texCoord': 0}
    material['pbrMetallicRoughness']['baseColorFactor'] = [1, 1, 1, 1]
    material.setdefault('extras', {}).update({
        'appearanceRole': 'shared-current-form-roof-material-family',
        'sourceImageSHA256': sha(swatch),
        'sourcePhoto': args.source_url,
        'registration': 'World-XZ material-family repeat; not measured finish or placement',
    })

    targets = []
    for node_i, mesh_i, world, _ in io.instances(gltf):
        for primitive_i, primitive in enumerate(gltf['meshes'][mesh_i]['primitives']):
            if primitive.get('material', 0) != args.material:
                continue
            position_i = primitive['attributes']['POSITION']
            positions = io.access(gltf, source_binary, position_i)
            world_positions = io.transform(positions, world)
            uv = np.ascontiguousarray(world_positions[:, [0, 2]] / args.repeat_metres, dtype='<f4')
            uv_view = view(uv.tobytes(), 34962)
            gltf.setdefault('accessors', []).append({'bufferView': uv_view, 'componentType': 5126,
                'count': len(uv), 'type': 'VEC2', 'min': uv.min(0).tolist(), 'max': uv.max(0).tolist()})
            primitive['attributes']['TEXCOORD_0'] = len(gltf['accessors'])-1
            targets.append({'nodeIndex': node_i, 'nodeName': gltf['nodes'][node_i].get('name'),
                'primitive': primitive_i, 'vertices': len(uv), 'positionAccessorUnchanged': position_i})
    if not targets:
        raise ValueError('No active primitive uses the selected material')

    gltf.setdefault('extras', {})['roofMaterialFamily'] = {
        'material': args.material, 'sourceAssetSHA256': source_sha,
        'swatchSHA256': sha(swatch), 'repeatMetres': args.repeat_metres,
        'scope': 'Appearance-family reuse on existing explicit roof/terrace surfaces; no geometry inference.'}
    raw = pack(gltf, binary)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(raw)
    after_gltf, after_binary, output_sha = io.read_glb(output)
    after_images = io.image_hashes(after_gltf, after_binary)
    if after_images[:-1] != before_images or after_images[-1] != sha(swatch):
        raise AssertionError('Existing images changed or swatch embedding failed')
    report = {'status': 'pass-isolated-candidate', 'sourceAssetSHA256': source_sha,
        'asset': {'url': output.name, 'sha256': output_sha, 'bytes': output.stat().st_size},
        'texture': {'sourceAsset': str(args.swatch), 'sourceURL': args.source_url,
            'sha256': sha(swatch), 'dimensions': dimensions, 'embeddedByteEqual': True},
        'material': args.material, 'repeatMetres': args.repeat_metres, 'targets': targets,
        'existingImagesByteUnchanged': True, 'geometryPositionAccessorsUnchanged': True,
        'limitations': ['Material-family reuse is not measured target-roof finish or placement.',
            'No roof equipment, parapet, drain, height or silhouette is added.',
            'Browser review is required; this report is not visual acceptance.']}
    output.with_suffix('.roof-swatch.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'asset': report['asset'], 'texture': report['texture'],
        'targetPrimitives': len(targets), 'targetVertices': sum(x['vertices'] for x in targets)}, indent=2))


if __name__ == '__main__':
    main()
