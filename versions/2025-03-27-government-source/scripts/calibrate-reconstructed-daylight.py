#!/usr/bin/env python3
"""Isolated display calibration and shared daylight for reused photo materials.

Original photographic bytes, UVs, geometry, identities and public source files
remain unchanged. The explicit colour profile is applied after image sampling;
normal-based lighting is stored in linear vertex colour, then the shared BVH
bakes actual inter-building and local geometric occlusion. Not measured sun or
intrinsic-image recovery. Never apply this to native photogrammetric radiance.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import struct
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('occlusion',ROOT/'scripts/bake-structure-shadows.py')
io=importlib.util.module_from_spec(spec);spec.loader.exec_module(io)


def pack(g,binary):
    g['buffers']=[{'byteLength':len(binary)}]
    encoded=json.dumps(g,separators=(',',':')).encode();encoded+=b' '*((-len(encoded))%4)
    binary=bytes(binary)+b'\0'*((-len(binary))%4)
    return struct.pack('<4sII',b'glTF',2,28+len(encoded)+len(binary))+struct.pack('<I4s',len(encoded),b'JSON')+encoded+struct.pack('<I4s',len(binary),b'BIN\0')+binary


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--colour-material',type=int,action='append',required=True,
        help='Material index receiving the shared display calibration; repeat for each photographic family')
    p.add_argument('--saturation',type=float,default=.45)
    args=p.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    if out.is_relative_to(ROOT/'public'):raise ValueError('Require isolated output')
    g,binary,digest=io.read_glb(args.source);binary=bytearray(binary)
    if g.get('extras',{}).get('structureOcclusionBake'):raise ValueError('Use source before any occlusion bake')
    original_images=io.image_hashes(g,binary);light=io.normalize(np.array([-.4,.8,.5]))
    profile={'saturation':args.saturation,'exposure':.96,'linearTint':[1.05,.95,1.0]}
    colour_materials=sorted(set(args.colour_material))
    if any(i<0 or i>=len(g.get('materials',[])) for i in colour_materials):
        raise ValueError('Colour material index out of range')
    for material_i in colour_materials:
        g['materials'][material_i].setdefault('extras',{})['campusPhotoCalibration']=profile
    for material in g['materials']:
        if 'baseColorTexture' in material.get('pbrMetallicRoughness',{}):
            material.setdefault('extras',{})['bakeStructureShadow']=True
            material['extras']['lightingInterpretation']='Reused photographic material family with fixed shared display daylight; not captured radiance for every elevation'
    records=[];seen=set()
    for ni,mi,world,extra in io.instances(g):
        if mi in seen:raise ValueError('Resolve instanced geometry before baking local normals')
        seen.add(mi)
        for pi,primitive in enumerate(g['meshes'][mi]['primitives']):
            attrs=primitive['attributes'];normal=io.access(g,binary,attrs['NORMAL'])
            normal=io.normalize(normal@np.linalg.inv(world[:3,:3]))
            multiplier=np.clip(.64+.46*np.maximum(0,normal@light),0,1)
            old=io.access(g,binary,attrs['COLOR_0']) if 'COLOR_0' in attrs else np.ones((len(normal),3))
            colour=np.ones(old.shape);colour[:,:3]=multiplier[:,None]
            if old.shape[1]==4:colour[:,3]=old[:,3]
            raw=colour.astype('<f4').tobytes();binary.extend(b'\0'*((-len(binary))%4));offset=len(binary);binary.extend(raw)
            vi=len(g['bufferViews']);g['bufferViews'].append({'buffer':0,'byteOffset':offset,'byteLength':len(raw)})
            ai=len(g['accessors']);g['accessors'].append({'bufferView':vi,'componentType':5126,'count':len(colour),'type':'VEC'+str(colour.shape[1])})
            attrs['COLOR_0']=ai
            records.append({'node':g['nodes'][ni].get('name'),'primitive':pi,'min':float(multiplier.min()),'max':float(multiplier.max())})
    g.setdefault('extras',{})['sharedDisplayDaylight']={'directionTowardLight':light.tolist(),'ambient':.64,'diffuse':.46,
        'sourceAssetSHA256':digest,'colourCalibration':profile,'scope':'Material-family display approximation; source JPEG/PNG bytes unchanged'}
    prepared=out/'daylight-input.glb';prepared.write_bytes(pack(g,binary))
    settings={'directionTowardLight':light.tolist(),'shadowDistanceM':250,'aoDistanceM':6,'surfaceOffsetM':.02,
        'aoRays':16,'aoStrength':.35,'shadowStrength':.28,'maximumEdgeM':1.5,
        'maximumOutputTriangles':350000,'maximumSamples':300000,
        'policy':'Fixed shared display daylight with source-material colour calibration; not measured campus illumination'}
    result=out/'ivillage-daylight.glb';bake=io.bake(prepared,result,settings)
    final,bb,final_sha=io.read_glb(result)
    assert io.image_hashes(final,bb)==original_images
    report={'sourceAssetSHA256':digest,'asset':{'url':result.name,'sha256':final_sha,'bytes':result.stat().st_size},
        'sourceImagesByteUnchanged':True,'colourProfile':profile,'colourProfileMaterialIds':colour_materials,'directionalRanges':records,
        'bake':bake,'visualAcceptance':False}
    (out/'calibration.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k]for k in ['asset','sourceImagesByteUnchanged','colourProfile']},indent=2))


if __name__=='__main__':main()
