#!/usr/bin/env python3
"""Validate current registry against a project, or a staged registry/exterior folder. No network."""
import argparse, collections, hashlib, json, math, struct
from pathlib import Path
from urllib.parse import urlsplit, unquote
from exterior_identity import exterior_entity_id, validate_exterior_identities
from current_form_contract import validate_current_form_set

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--project',required=True,type=Path)
    ap.add_argument('--registry',type=Path,help='Defaults to PROJECT/public/data/entity-registry.json')
    ap.add_argument('--resources',type=Path)
    ap.add_argument('--exteriors',type=Path,help='Optional staged /path/manifest.json override for /models/exteriors/')
    ap.add_argument('--sports',type=Path,help='Optional staged sports manifest.json override for /surfaces/sports/')
    ap.add_argument('--outdoor',type=Path,help='Defaults to outdoor-entities.json next to registry, then project public/data/')
    ap.add_argument('--report',type=Path,help='Optional JSON report file; otherwise stdout only')
    args=ap.parse_args();project=args.project.resolve();public=project/'public'
    registry_file=(args.registry or public/'data/entity-registry.json').resolve()
    registry=json.loads(registry_file.read_text());resources_file=args.resources or registry_file.parent/registry['resourcesUrl']
    if not resources_file.exists() and not args.resources:resources_file=public/'data'/registry['resourcesUrl']
    resources=json.loads(resources_file.read_text())
    outdoor_file=args.outdoor or registry_file.parent/'outdoor-entities.json'
    if not outdoor_file.exists() and not args.outdoor:outdoor_file=public/'data/outdoor-entities.json'
    outdoor=json.loads(outdoor_file.read_text());outdoor_roads={x['streetCode']:x for x in outdoor['roads']};outdoor_surfaces={x['sourceEntityId']:x for x in outdoor['surfaces']}
    sports_file=(args.sports or public/'surfaces/sports/manifest.json').resolve();sports=json.loads(sports_file.read_text())
    sport_features={x['entityId']:x for x in sports['features']}
    exterior_file=(args.exteriors or public/'models/exteriors/manifest.json').resolve()
    exterior=json.loads(exterior_file.read_text());bundles={b['id']:b for b in exterior['bundles']}
    errors=[];warnings=[];current_form_details=[];landmark_details=[];checked_files=set();gltf_checked=set();reps={};room_owners=collections.Counter();room_floor_cache={}
    try:validate_exterior_identities(exterior['bundles'])
    except ValueError as exc:errors.append(str(exc))
    def check(ok,message):
        if not ok:errors.append(message)
    def asset_path(asset):
        if asset.startswith('/models/exteriors/') and args.exteriors:return exterior_file.parent/asset.removeprefix('/models/exteriors/')
        if asset.startswith('/surfaces/sports/') and args.sports:return sports_file.parent/asset.removeprefix('/surfaces/sports/')
        if asset=='/data/outdoor-entities.json':return outdoor_file
        if asset=='/data/entity-registry-pois.json' and (registry_file.parent/'entity-registry-pois.json').exists():return registry_file.parent/'entity-registry-pois.json'
        return public/asset.lstrip('/')
    def exists(asset):
        if asset.startswith('/api/') or urlsplit(asset).scheme:return None
        p=asset_path(asset);check(p.is_file(),'missing asset: '+str(p));checked_files.add(str(p));return p
    def bounds_valid(bounds,label):
        check(all(isinstance(x,(int,float)) and math.isfinite(x) for side in ('min','max') for x in bounds[side]),'nonfinite bounds '+label)
        check(all(a<=b for a,b in zip(bounds['min'],bounds['max'])),'reversed bounds '+label)
    def check_model(asset,sha=None):
        p=exists(asset)
        if p is None or not p.is_file() or str(p) in gltf_checked:return
        gltf_checked.add(str(p));data=p.read_bytes()
        if sha:check(hashlib.sha256(data).hexdigest()==sha,'model SHA mismatch '+asset)
        if p.suffix=='.glb':
            check(len(data)>=12 and data[:4]==b'glTF','invalid GLB magic '+asset)
            if len(data)>=12:check(struct.unpack_from('<II',data,4)==(2,len(data)),'invalid GLB version/length '+asset)
            jlength=struct.unpack_from('<I',data,12)[0];gltf=json.loads(data[20:20+jlength])
        else:gltf=json.loads(data)
        check(gltf['asset']['version']=='2.0','glTF version '+asset)
        for kind in ('buffers','images'):
            for ref in gltf.get(kind,[]):
                uri=ref.get('uri')
                if not uri or uri.startswith('data:'):continue
                check(not urlsplit(uri).scheme,'nonlocal glTF dependency '+uri)
                dep=(p.parent/unquote(uri)).resolve();check(dep.is_file(),'missing glTF dependency '+str(dep));checked_files.add(str(dep))
                if dep.exists() and kind=='buffers':check(dep.stat().st_size>=ref['byteLength'],'short buffer '+str(dep))
    def check_current_form(eid,e,r):
        """Verify the explicitly approximate local mesh without promoting it to a source exterior bundle."""
        label='current form '+r['id'];start_errors=len(errors)
        manifest_asset=r.get('sourceManifest');check(isinstance(manifest_asset,str),label+' missing sourceManifest')
        if not isinstance(manifest_asset,str):return
        manifest_path=exists(manifest_asset)
        if manifest_path is None or not manifest_path.is_file():return
        m=json.loads(manifest_path.read_text());bid=e['externalIds'].get('pathAdvisorBuildingId')
        check(e['type']=='building' and m.get('entityId')==eid and m.get('buildingId')==bid,label+' physical entity binding')
        check(r.get('featureId')==bid and m.get('subtype')==r.get('subtype'),label+' source feature/subtype')
        check(m.get('name') in [e.get('name')]+e.get('aliases',[]),label+' canonical name/alias')
        check(registry['legacyMap'].get(m.get('catalogId'))==eid,label+' legacy binding')
        expected_asset=str(Path(manifest_asset).parent/m['url'])
        check(r['asset']==expected_asset,label+' model/manifest URL binding')
        check(r.get('bounds')==m.get('bounds'),label+' representation bounds')
        coordinate=m.get('coordinateSystem',{});check(coordinate.get('alreadyLocal') is True and coordinate.get('applyAdditionalTransform') is False,label+' local transform declaration')
        check(coordinate.get('originEN')==[844800,820500],label+' local origin')
        runtime=m.get('runtime',{});check(runtime.get('selectionEntityId')==eid and runtime.get('hideEntireGroupWhenOpenedBuildingId')==bid,label+' indoor visibility/selection binding')
        check(not any(k in r for k in ('offset','matrix')),label+' unexpected extra representation transform')
        params=m.get('approximationParameters',{});check(params.get('roofHeightMeasured') is False,label+' approximate roof misrepresented as measured')
        source_records=m.get('sources',{}).get('savedGeometry',[]);source_assets={x.get('asset') for x in source_records};source_hashes=0
        check(len(source_assets)==len(source_records),label+' duplicate source assets')
        for source in source_records:
            p=exists(source['asset']);digest=source.get('sha256');check(isinstance(digest,str) and len(digest)==64,label+' missing source SHA '+source['asset'])
            if p and p.is_file():check(hashlib.sha256(p.read_bytes()).hexdigest()==digest,label+' source SHA mismatch '+source['asset']);source_hashes+=1
        check('/data/building-footprints.json' in source_assets and '/interiors/manifest.json' in source_assets,label+' missing geometric source manifests')
        source_manifest=json.loads((public/'interiors/manifest.json').read_text());source_meta=[x for x in source_manifest['floors'] if x['buildingId']==bid];floor_sources={}
        for f in source_meta:
            asset='/interiors/'+f['url'];check(asset in source_assets,label+' omitted original floor '+f['id']);floor_sources[f['id']]=json.loads(asset_path(asset).read_text())
        zs=sorted({z for f in floor_sources.values() for z in f['sourceZValues']});source_parts=sum(len(f['rooms']) for f in floor_sources.values());summary=m.get('sourceFloorGeometry',{})
        check(r.get('sourceZValues')==zs and summary.get('sourceZValues')==zs,label+' sourceZ flattened or schematic roof mixed into sourceZ')
        check(summary.get('floorCount')==len(floor_sources) and summary.get('publicPolygonParts')==source_parts,label+' source floor/part coverage')
        check(params.get('highestSourceFloorY')==max(zs) and params.get('bottomY')==min(zs),label+' source elevation extent')
        check(math.isclose(params.get('schematicRoofY',math.nan),max(zs)+params.get('schematicTopExtensionMeters',math.nan)),label+' schematic top extension')
        check_model(r['asset'],m.get('sha256'));model_path=asset_path(r['asset']);raw=model_path.read_bytes();check(m.get('geometryBytes')==len(raw),label+' model byte count')
        chunks={};cursor=12
        while cursor+8<=len(raw):
            length,kind=struct.unpack_from('<I4s',raw,cursor);cursor+=8;check(cursor+length<=len(raw),label+' truncated GLB chunk');chunks[kind]=raw[cursor:cursor+length];cursor+=length
        check(cursor==len(raw) and b'JSON' in chunks and b'BIN\0' in chunks,label+' complete GLB chunks')
        gltf=json.loads(chunks[b'JSON']);binary=chunks[b'BIN\0']
        texture_records=m.get('appearanceTextures',[]);textured=bool(texture_records);texture_checks=[];source_gltf=source_binary=None
        if textured:
            check(m.get('version')==2 and m.get('textures')==2 and len(texture_records)==2 and len(gltf.get('images',[]))==len(gltf.get('textures',[]))==2,label+' authorized facade texture count')
            check({x.get('asset')for x in texture_records}=={'textures/facade-broad-photo-derived.png','textures/facade-end-photo-derived.png'},label+' unexpected facade texture asset')
            generation=m.get('sources',{}).get('textureGeneration',{});check(generation.get('tool')=='built-in image_gen' and generation.get('notOriginalPhotographicPixels') is True,label+' generated texture origin missing')
            prompt_path=exists(str(Path(manifest_asset).parent/generation.get('promptAsset','missing')))
            if prompt_path and prompt_path.is_file():
                prompt=json.loads(prompt_path.read_text());check(prompt.get('tool')=='built-in image_gen' and len(prompt.get('outputs',[]))==2 and all(x.get('prompt')for x in prompt.get('outputs',[])),label+' generation prompts missing')
            for i,texture in enumerate(texture_records):
                asset=str(Path(manifest_asset).parent/texture['asset']);path=exists(asset)
                if path is None or not path.is_file():continue
                data=path.read_bytes();check(hashlib.sha256(data).hexdigest()==texture.get('sha256'),label+' facade texture SHA '+asset)
                check(data[:8]==b'\x89PNG\r\n\x1a\n',label+' facade PNG header');dimensions=list(struct.unpack_from('>II',data,16));check(dimensions==texture.get('dimensions'),label+' facade dimensions')
                image=gltf['images'][i];view=gltf['bufferViews'][image['bufferView']];embedded=binary[view.get('byteOffset',0):view.get('byteOffset',0)+view['byteLength']]
                check(image.get('mimeType')=='image/png' and 'uri' not in image and embedded==data,label+' offline embedded texture differs from saved texture')
                check(gltf['textures'][i].get('source')==i,label+' texture source index');texture_checks.append({'asset':asset,'dimensions':dimensions,'sha256':hashlib.sha256(data).hexdigest(),'embeddedByteEqual':embedded==data})
            original=m.get('sourceGeometryAsset',{});original_path=exists(str(Path(manifest_asset).parent/original.get('asset','missing')))
            expected_original_sha='518945726d20cd4b4147c09730807b4cc6a1db6c9638e9d919372b021b6999bf'
            check(original.get('sha256')==expected_original_sha and original.get('positionsAndNormalsUnchanged') is True,label+' original geometry lock')
            if original_path and original_path.is_file():
                original_bytes=original_path.read_bytes();check(hashlib.sha256(original_bytes).hexdigest()==expected_original_sha,label+' original geometry changed');jlength=struct.unpack_from('<I',original_bytes,12)[0];source_gltf=json.loads(original_bytes[20:20+jlength]);blength=struct.unpack_from('<I',original_bytes,20+jlength)[0];source_binary=original_bytes[28+jlength:28+jlength+blength]
                check(gltf['nodes']==source_gltf['nodes'],label+' source nodes/extras/transforms changed')
            check(m.get('uvRegistration',{}).get('sourceWorldPositionsChanged') is False and m.get('uvRegistration',{}).get('absoluteFacadeSideRegistrationMeasured') is False,label+' UV registration boundary')
        else:check(not gltf.get('images') and not gltf.get('textures') and m.get('textures')==0,label+' reference photo incorrectly became texture')
        check(gltf.get('extras',{}).get('entityId')==eid,label+' GLB root entity binding')
        def positions(accessor_index):
            accessor=gltf['accessors'][accessor_index];check(accessor['componentType']==5126 and accessor['type']=='VEC3',label+' position accessor layout')
            view=gltf['bufferViews'][accessor['bufferView']];check(view.get('buffer',0)==0,label+' unexpected buffer');stride=view.get('byteStride',12);offset=view.get('byteOffset',0)+accessor.get('byteOffset',0);count=accessor['count']
            check(offset+max(count-1,0)*stride+12<=view.get('byteOffset',0)+view['byteLength']<=len(binary),label+' accessor buffer bounds')
            result=[struct.unpack_from('<fff',binary,offset+i*stride) for i in range(count)]
            check(all(math.isfinite(v) for p in result for v in p),label+' nonfinite GLB positions');return result
        def original_attribute(index):
            a=source_gltf['accessors'][index];v=source_gltf['bufferViews'][a['bufferView']];offset=v.get('byteOffset',0)+a.get('byteOffset',0);stride=v.get('byteStride',12)
            return [struct.unpack_from('<fff',source_binary,offset+i*stride)for i in range(a['count'])]
        def validate_facade_uv(primitive,vertex_count):
            index=primitive.get('attributes',{}).get('TEXCOORD_0');check(isinstance(index,int),label+' facade UV missing')
            if not isinstance(index,int):return
            a=gltf['accessors'][index];v=gltf['bufferViews'][a['bufferView']];check(a['componentType']==5126 and a['type']=='VEC2' and a['count']==vertex_count,label+' facade UV layout');offset=v.get('byteOffset',0)+a.get('byteOffset',0);stride=v.get('byteStride',8)
            coords=[struct.unpack_from('<ff',binary,offset+i*stride)for i in range(a['count'])];check(all(math.isfinite(x) and 0<=x<=1 for uv in coords for x in uv),label+' facade UV outside image')
            material=gltf['materials'][primitive['material']];binding=material.get('pbrMetallicRoughness',{}).get('baseColorTexture',{});check(binding.get('index') in (0,1) and binding.get('texCoord',0)==0,label+' facade material texture binding')
        def ring_area(ring):
            if len(ring)<3:return 0
            x,z=ring[0];return abs(sum((a[0]-x)*(b[1]-z)-(b[0]-x)*(a[1]-z) for a,b in zip(ring,ring[1:]+ring[:1])))/2
        mesh_count=triangles=0;all_positions=[];actual_floors={};area_checks=[];roles=collections.Counter()
        for node in gltf['nodes']:
            if 'mesh' not in node:continue
            check(not any(k in node for k in ('matrix','translation','rotation','scale')),label+' extra node transform')
            extra=node.get('extras',{});check(extra.get('entityId')==eid,label+' GLB node entity');check(extra.get('hideWhenBuildingOpened') is True,label+' node indoor hiding policy');role=extra.get('representationRole');roles[role]+=1
            check(role in ('exact_source_floor_parts','approximate_exterior_band','approximate_roof_cap'),label+' unclassified source/approximate node')
            mesh_count+=1;node_positions=[];original_faces=[]
            for primitive in gltf['meshes'][node['mesh']]['primitives']:
                check(primitive.get('mode',4)==4 and 'indices' not in primitive,label+' expected nonindexed triangle geometry')
                pts=positions(primitive['attributes']['POSITION']);check(len(pts)%3==0,label+' triangle vertex count');triangles+=len(pts)//3;node_positions.extend(pts);all_positions.extend(pts)
                if textured and source_gltf is not None:
                    source_primitive=source_gltf['meshes'][node['mesh']]['primitives'][0];source_points=original_attribute(source_primitive['attributes']['POSITION']);source_normals=original_attribute(source_primitive['attributes']['NORMAL'])
                    if role=='approximate_exterior_band':
                        validate_facade_uv(primitive,len(pts));face_ids=primitive.get('extras',{}).get('sourceTriangleIndices',[]);check(len(face_ids)*3==len(pts) and all(isinstance(i,int) and 0<=i<len(source_points)//3 for i in face_ids),label+' facade source face map');original_faces.extend(face_ids)
                        expected_points=[point for i in face_ids for point in source_points[i*3:i*3+3]];expected_normals=[normal for i in face_ids for normal in source_normals[i*3:i*3+3]]
                    else:expected_points=source_points;expected_normals=source_normals
                    check(pts==expected_points and positions(primitive['attributes']['NORMAL'])==expected_normals,label+' original POSITION/NORMAL changed '+node.get('name',''))
            if textured and role=='approximate_exterior_band' and source_gltf is not None:check(sorted(original_faces)==list(range(len(source_points)//3)),label+' source facade face duplicated or omitted')
            if role=='exact_source_floor_parts':
                fid=extra.get('sourceFloorId');check(fid in floor_sources,label+' unknown source floor node')
                if fid not in floor_sources:continue
                f=floor_sources[fid];actual_floors[fid]=actual_floors.get(fid,0)+1;check(extra.get('sourceZValues')==f['sourceZValues'],label+' node sourceZ metadata')
                check(extra.get('roomPartIndices')==list(range(len(f['rooms']))),label+' source part index coverage')
                allowed={(round(p[0],3),round(room['heightSourceZ'],3),round(p[1],3)) for room in f['rooms'] for ring in room['rings'] for p in ring}
                check(all(tuple(round(v,3) for v in p) in allowed for p in node_positions),label+' floor vertex not from source ring '+fid)
                check(all(any(abs(p[1]-z)<0.0001 for z in f['sourceZValues']) for p in node_positions),label+' moved source floor Z '+fid)
                source_area=sum(ring_area(room['rings'][0])-sum(ring_area(hole) for hole in room['rings'][1:]) for room in f['rooms']);actual_area=0;roundoff_bound=0
                epsilon=0.000062
                for a,b,c in zip(node_positions[::3],node_positions[1::3],node_positions[2::3]):
                    actual_area+=abs((b[0]-a[0])*(c[2]-a[2])-(b[2]-a[2])*(c[0]-a[0]))/2
                    roundoff_bound+=math.sqrt(2)*epsilon*(math.hypot(b[0]-a[0],b[2]-a[2])+math.hypot(c[0]-a[0],c[2]-a[2]))+4*epsilon*epsilon
                difference=abs(source_area-actual_area);check(difference<=roundoff_bound+1e-7,label+' source floor area mismatch '+fid);area_checks.append({'floorId':fid,'sourceAreaM2':source_area,'float32MeshAreaM2':actual_area,'absoluteDifferenceM2':difference,'conservativeFloat32AreaToleranceM2':roundoff_bound})
            elif role=='approximate_roof_cap':check(extra.get('heightIsMeasured') is False,label+' roof node measurement claim')
        check(set(actual_floors)==set(floor_sources) and all(v==1 for v in actual_floors.values()),label+' exact floor layer coverage')
        actual_bounds={'min':[min(p[i] for p in all_positions) for i in range(3)],'max':[max(p[i] for p in all_positions) for i in range(3)]};check(actual_bounds==m['bounds'],label+' actual vertex bounds')
        check(mesh_count==m['meshes'] and triangles==m['triangles'],label+' mesh/triangle counts')
        photo_checks=[]
        for photo in m['sources'].get('officialExteriorPhotos',[]):
            photo_asset=str(Path(manifest_asset).parent/photo['localFile']);p=exists(photo_asset)
            if p is None or not p.is_file():continue
            data=p.read_bytes();check(hashlib.sha256(data).hexdigest()==photo.get('sha256'),label+' photo SHA '+photo_asset)
            # JPEG SOF dimensions; no image decoder dependency or network needed.
            check(data[:2]==b'\xff\xd8',label+' source photo JPEG header');i=2;dimensions=None
            while i+4<=len(data):
                if data[i]!=255:i+=1;continue
                while i<len(data) and data[i]==255:i+=1
                if i>=len(data):break
                marker=data[i];i+=1
                if marker in (0xd8,0xd9,0x01) or 0xd0<=marker<=0xd7:continue
                length=struct.unpack_from('>H',data,i)[0]
                if marker in (0xc0,0xc1,0xc2,0xc3,0xc5,0xc6,0xc7,0xc9,0xca,0xcb,0xcd,0xce,0xcf):
                    height,width=struct.unpack_from('>HH',data,i+3);dimensions=[width,height];break
                if length<2:break
                i+=length
            check(dimensions==photo.get('dimensions'),label+' source photo dimensions '+photo_asset)
            matches=[res for res in resources['resources'] if res.get('type')=='photo' and res.get('asset')==photo_asset and res.get('sourceImage')==photo.get('url') and any(binding.get('entityId')==eid and binding.get('relation')=='depicts' for binding in res.get('bindings',[]))]
            check(len(matches)==1,label+' photo resource depicts/source binding '+photo_asset)
            check(all(res.get('captureDate') is None for res in matches) and photo.get('filenameDateNotCertifiedCaptureDate') is True,label+' unsupported photo capture date')
            photo_checks.append({'asset':photo_asset,'dimensions':dimensions,'sha256':hashlib.sha256(data).hexdigest(),'resourceIds':[res['resourceId'] for res in matches]})
        check(len(photo_checks)==2,label+' expected two inspected official exterior photos')
        current_form_details.append({'entityId':eid,'representationId':r['id'],'asset':r['asset'],'manifest':manifest_asset,'status':'pass' if len(errors)==start_errors else 'fail','sourceGeometryHashesChecked':source_hashes,'sourceFloorLayers':len(actual_floors),'sourcePolygonParts':source_parts,'sourceZValues':zs,'meshes':mesh_count,'triangles':triangles,'nodeRoles':dict(roles),'bounds':actual_bounds,'floorAreaChecks':area_checks,'referencePhotos':photo_checks,'facadeTextures':texture_checks,'originalSourceGeometryPreserved':textured and source_gltf is not None,'roofHeightMeasured':False})

    def check_landmark(eid,e,r):
        label='landmark '+r['id'];start_errors=len(errors);manifest_asset=r['sourceManifest'];mp=exists(manifest_asset)
        if not mp or not mp.is_file():return
        m=json.loads(mp.read_text());base=Path(manifest_asset).parent
        check(e['type']=='facility' and e.get('function')=='landmark' and e.get('subtype')=='sundial_sculpture',label+' physical type/function')
        check(m['entityId']==eid and m['parentId']==e['parentId']==registry['legacyMap']['campus-61'],label+' piazza/physical binding')
        check(entities[e['parentId']]['type']=='outdoor_area' and any(x['type']=='locatedIn' and x['targetId']==e['parentId'] for x in e['relations']),label+' locatedIn piazza')
        check(m['approximation'] is True and m['parameters']['steelThicknessMeasured'] is False,label+' approximation boundary')
        check(m['sourceHeightMeters']==8.5 and m['parameters']['totalHeight']==8.5,label+' published height')
        check(r['asset']==str(base/m['url']) and r['bounds']==m['bounds'],label+' asset/bounds binding')
        check_model(r['asset'],m['sha256']);raw=asset_path(r['asset']).read_bytes();jn=struct.unpack_from('<I',raw,12)[0];g=json.loads(raw[20:20+jn]);bn=struct.unpack_from('<I',raw,20+jn)[0];binary=raw[28+jn:28+jn+bn]
        check(not g.get('images') and not g.get('textures'),label+' photos incorrectly mapped as textures')
        pts=[];body_pts=[];triangles=mesh_count=0;roles=collections.Counter()
        for node in g['nodes']:
            check(not any(k in node for k in ('matrix','translation','rotation','scale')),label+' extra local transform')
            if 'mesh' not in node:continue
            extra=node.get('extras',{});check(extra.get('entityId')==eid and extra.get('approximation') is True,label+' node identity/approximation');roles[extra.get('representationRole')]+=1;mesh_count+=1
            for primitive in g['meshes'][node['mesh']]['primitives']:
                accessor=g['accessors'][primitive['attributes']['POSITION']];check(accessor['componentType']==5126 and accessor['type']=='VEC3',label+' position layout');view=g['bufferViews'][accessor['bufferView']];offset=view.get('byteOffset',0)+accessor.get('byteOffset',0);stride=view.get('byteStride',12)
                points=[struct.unpack_from('<fff',binary,offset+i*stride) for i in range(accessor['count'])];check(all(math.isfinite(v) for p in points for v in p),label+' nonfinite positions');pts.extend(points);triangles+=(g['accessors'][primitive['indices']]['count'] if 'indices' in primitive else len(points))//3
                if extra.get('representationRole')=='community_reconstructed_sculpture':body_pts.extend(points)
        actual={'min':[min(p[i] for p in pts) for i in range(3)],'max':[max(p[i] for p in pts) for i in range(3)]}
        check(actual==m['bounds'] and mesh_count==m['meshes'] and triangles==m['triangles'],label+' actual geometry bounds/counts')
        height=actual['max'][1]-actual['min'][1];check(abs(height-8.5)<.0001,label+' actual official-height constraint')
        position=m['positionEvidence'];polygon_asset=str(base/position['sourceAsset']);polygon=exists(polygon_asset)
        check(polygon and hashlib.sha256(polygon.read_bytes()).hexdigest()==position['sourceSHA256'],label+' official position source SHA')
        check(position['sourceId']==r['featureId']=='1101824872' and m['position']==r['position'],label+' source position binding')
        for filename,digest in m['sourceHash'].items():
            p=exists(str(base/filename));check(p and hashlib.sha256(p.read_bytes()).hexdigest()==digest,label+' source inspection SHA '+filename)
        community=m['sources']['communityModel'];check(community['license']=='MIT' and community['commit']=='8d42b92cca54d9da26f75b0f7ea4fd6adea3168e',label+' community license/version')
        for record in community['files']:
            p=exists(str(base/record['asset']));check(p and hashlib.sha256(p.read_bytes()).hexdigest()==record['sha256'],label+' community source SHA '+record['asset'])
        stl=asset_path(str(base/'community-source/redBird_OpenSCAD.stl')).read_bytes();source_count=struct.unpack_from('<I',stl,80)[0];expected=[];discarded=0;cut=m['parameters']['sourcePrintingSupportTop'];scale=m['parameters']['scaleMetersPerSourceUnit'];angle=math.radians(m['parameters']['orientationDegrees']);origin=m['position']
        for ti in range(source_count):
            source_points=[struct.unpack_from('<fff',stl,84+50*ti+12+12*j) for j in range(3)]
            if all(p[2]<=cut+1e-7 for p in source_points):discarded+=1;continue
            check(all(p[2]>=cut for p in source_points),label+' unexpected source facet crossing; validator must implement clipping before accepting')
            expected.extend(((x*math.cos(angle)+y*math.sin(angle))*scale+origin[0],(z-cut)*scale+origin[1],(x*math.sin(angle)-y*math.cos(angle))*scale+origin[2]) for x,y,z in source_points)
        check(len(expected)==len(body_pts),label+' community retained facet count');max_error=max((abs(a-b) for p,q in zip(expected,body_pts) for a,b in zip(p,q)),default=math.inf);check(max_error<.0001,label+' body vertices differ from registered community source')
        check(discarded==m['parameters']['discardedPrintingSupportTriangles'],label+' printing support removal count')
        photo_checks=[]
        for photo in m['sources']['photos']:
            asset=str(base/photo['asset']);p=exists(asset);check(p and hashlib.sha256(p.read_bytes()).hexdigest()==photo['sha256'],label+' photo SHA '+asset)
            matches=[res for res in resources['resources'] if res.get('asset')==asset and res.get('sourceImage')==photo['url']];check(len(matches)==1,label+' unique source photo resource '+asset)
            for res in matches:
                relation='depicts' if photo['purpose']=='sculpture form detail' else 'nearby';check(any(b['entityId']==eid and b['relation']==relation for b in res['bindings']),label+' detail/context resource distinction '+asset)
                if relation=='nearby':check(any(b['entityId']==e['parentId'] and b['relation']=='depicts' for b in res['bindings']),label+' wide photo piazza subject')
                check(res.get('captureDate')==photo.get('captureDate'),label+' historical photo date')
            photo_checks.append(asset)
        check(len(photo_checks)==6,label+' six official photo references')
        landmark_details.append({'entityId':eid,'status':'pass' if len(errors)==start_errors else 'fail','meshes':mesh_count,'triangles':triangles,'actualHeight':height,'officialPublishedHeight':8.5,'bounds':actual,'photoResources':len(photo_checks),'roles':dict(roles),'notSurveyCAD':True,'communitySourceTriangles':source_count,'removedPrintingSupportTriangles':discarded,'maxRegisteredVertexDifferenceMeters':max_error})

    entities={e['entityId']:e for e in registry['entities']};check(len(entities)==len(registry['entities']),'duplicate entityId')
    range_domains=json.loads((public/'data/picking/building-domains-extra.json').read_text())['auditOnlyAggregateDomains']
    catalog=json.loads((public/'data/catalog.json').read_text());check(set(registry['legacyMap'])=={x['id'] for x in catalog['buildings']},'legacy catalog coverage')
    for cid,eid in registry['legacyMap'].items():check(eid in entities,'legacy reference '+cid)
    locations=collections.defaultdict(set);ambiguous=collections.defaultdict(set);mesh_entities=[];stop_count=0;sports_reps=[];road_reps=[]
    for eid,e in entities.items():
        seen=set();cursor=eid
        while cursor:
            check(cursor in entities,'unknown parent '+str(cursor))
            if cursor not in entities:break
            if cursor in seen:errors.append('parent cycle '+eid);break
            seen.add(cursor);cursor=entities[cursor]['parentId']
        for rel in e['relations']:check(rel['targetId'] in entities,'relation target '+eid)
        ext=e['externalIds']
        for lid in [ext.get('locationId')]+ext.get('locationIds',[]):
            if lid:locations[lid].add(eid)
        for lid in ext.get('ambiguousLocationIds',[]):ambiguous[lid].add(eid)
        if e.get('function')=='toilet':check(e['type']=='space','toilet duplicated as nonspace '+eid)
        for r in e['representations']:
            check(r['id'] not in reps,'duplicate representationId '+r['id']);reps[r['id']]=(eid,r);exists(r['asset'])
            if 'bounds' in r:bounds_valid(r['bounds'],r['id'])
            if r['type']=='room_parts':
                floorid=entities[r['floorId']]['externalIds']['pathAdvisorFloorId']
                if floorid not in room_floor_cache:room_floor_cache[floorid]=json.loads(asset_path(r['asset']).read_text())
                floor=room_floor_cache[floorid];featureids=r['featureId'] if isinstance(r['featureId'],list) else [r['featureId']]
                zs=set()
                for pi in r['partIndices']:
                    check(0<=pi<len(floor['rooms']),'invalid partIndex '+r['id'])
                    if not 0<=pi<len(floor['rooms']):continue
                    part=floor['rooms'][pi];check(part['interactive'],'background made into room entity')
                    check(part['sourceLocationId'] in featureids,'source location mismatch '+r['id']);room_owners[(floorid,pi)]+=1
                    if part['heightSourceZ'] is not None:zs.add(part['heightSourceZ'])
                check(set(r['sourceZValues'])==zs,'flattened room Z '+r['id'])
            elif r['type']=='floor_drawing':
                floor=json.loads(asset_path(r['asset']).read_text());check(e['externalIds']['pathAdvisorFloorId']==floor['id'],'floor source ID mismatch')
                check(e['sourceZ']==floor['z'] and e['sourceZValues']==floor['sourceZValues'],'flattened floor Z '+eid)
            elif r['type']=='mesh_surface' and r.get('subtype')=='orthophoto_dtm_surface':
                sports_reps.append(eid);check(e['type']=='outdoor_area','sport surface entity type')
                sid=r['featureId'];check(sid in sport_features and sid in outdoor_surfaces,'sport source feature exists')
                check(outdoor['surfaceNodeEntityMap'].get(sid)==eid,'surface node canonical mapping')
                if sid in sport_features:
                    sf=sport_features[sid];check(r['bounds']==sf['meshBounds'],'surface bounds preserved')
                    check(e['externalIds']['iB1000PolygonId']==str(sf['sourcePolygonId']),'surface source polygon identity')
                    check(r['offset']==[0,0,0],'sports surface offset invented')
                    if sf.get('campusId')=='campus-52':check(e['parentId']==registry['legacyMap']['campus-52'],'stadium surface containment')
                check_model(r['asset']);raw=asset_path(r['asset']).read_bytes();jn=struct.unpack_from('<I',raw,12)[0];gltf=json.loads(raw[20:20+jn]);matches=[n for n in gltf['nodes'] if n.get('extras',{}).get('entityId')==sid]
                check(len(matches)==1 and matches[0]['name']==r['nodeName'],'actual sports GLB node match')
                check(outdoor_surfaces[sid]['boundaryLocalXZ']==sport_features[sid]['sourceBoundary'],'surface source rings unchanged')
            elif r['type']=='line_group' and r.get('subtype')=='official_streetcentreline':
                road_reps.append(eid);check(e['type']=='path','street centreline entity type');road=outdoor_roads.get(r['featureId']);check(road is not None,'street code reference')
                if road:
                    check(road['entityId']==eid,'street physical ID mismatch');check(e['externalIds']['officialStreetCode']==road['streetCode'],'official street code mismatch')
                    check(len(road['linesLocalXZ'])==len(road['segments']),'street lines/metadata mismatch')
                    for segment,line in zip(road['segments'],road['linesLocalXZ']):
                        check(len(line)>=2 and all(len(pt)==2 and all(math.isfinite(v) for v in pt) for pt in line),'valid local XZ source line')
                        check(segment['deckHeight'] is None,'invented deck height')
                        check(segment['streetType']!='Tunnel' or not segment['displayGroundReference'],'tunnel incorrectly draped as ground')
                        sm=outdoor['roadSourceMap'].get(segment['streetCentrelineId']);check(sm is not None and sm['entityId']==eid and sm['lineIndex']==segment['lineIndex'],'road original segment mapping')
            elif r['type']=='mesh' and r.get('subtype')=='unified_current_form_approximation':
                try:current_form_details.append(validate_current_form_set(project,e,r))
                except (OSError,ValueError,KeyError,IndexError,TypeError,StopIteration,struct.error) as exc:errors.append('invalid complete current form '+r['id']+': '+str(exc))
            elif r['type']=='mesh' and r.get('subtype')=='public_floor_based_current_form_approximation':
                try:check_current_form(eid,e,r)
                except (OSError,ValueError,KeyError,IndexError,TypeError,struct.error) as exc:errors.append('invalid current form '+r['id']+': '+str(exc))
            elif r['type']=='mesh' and r.get('subtype')=='photo_roof_based_current_form_approximation':
                manifest_asset=r.get('sourceManifest');m=json.loads(asset_path(manifest_asset).read_text());b=next((b for b in m['buildings'] if b['entityId']==eid),None)
                protection=m.get('sourceProtection')
                if protection:
                    base=Path(manifest_asset).parent
                    protection_path=exists(str(base/protection['url']))
                    checked_descriptor=json.loads(asset_path(str(base/'source-protection.json')).read_text())
                    check(checked_descriptor==protection,'Hall source protection static/runtime manifest binding')
                    check(protection['encoding']=='rg-ground-uint16-256-ba-structure-int-255-absent','Hall independent protection channel encoding')
                    if protection_path:
                        data=protection_path.read_bytes()
                        check(len(data)==protection['width']*protection['height']*4==protection['bytes'],'Hall source protection raw dimensions')
                        check(hashlib.sha256(data).hexdigest()==protection['sha256'],'Hall source protection raw SHA')
                        check(sum(data[i]>0 for i in range(0,len(data),4))==protection['groundPixels'],'Hall source ground pixel count')
                        check(sum(data[i+2]<255 and data[i+3]<255 for i in range(0,len(data),4))==protection['structurePixels'],'Hall independent UGX pixel count')
                    ground=asset_path('/surfaces/ground-reference/ground-reference.png')
                    check(hashlib.sha256(ground.read_bytes()).hexdigest()==protection['unchangedGroundReferenceSHA256'],'existing ground-reference bytes changed during Hall fix')
                check(b is not None,'current hall canonical identity '+eid)
                if b:
                    check(r['asset']==str(Path(manifest_asset).parent / b['url']),'current hall asset binding '+eid)
                    check(r['bounds']==b['bounds'],'current hall bounds '+eid)
                    check(r['sourceZValues']==b['sourceFloorZValues'],'current hall source floor Z '+eid)
                    check_model(r['asset'],b['sha256'])
                    for f in b['sourceFloors']:
                        raw=asset_path(f['asset']).read_bytes();check(hashlib.sha256(raw).hexdigest()==f['sha256'],'current hall original source floor hash '+eid)
                    check(m['parameters']['roofMeasured'] is False,'current hall approximate roof boundary '+eid)
                    current_form_details.append({'entityId':eid,'asset':r['asset'],'status':'pass','roofHeightMeasured':False,'sourceFloorLayers':len(b['sourceFloors'])})
            elif r['type']=='mesh' and r.get('subtype')=='photo_referenced_landmark_approximation':
                try:check_landmark(eid,e,r)
                except (OSError,ValueError,KeyError,IndexError,TypeError,struct.error) as exc:errors.append('invalid landmark '+r['id']+': '+str(exc))
            elif r['type']=='mesh_group':
                mesh_entities.append(eid);b=bundles.get(r['featureId']);check(b is not None,'missing exterior bundle')
                if not b:continue
                try:owner=exterior_entity_id(b)
                except ValueError as exc:errors.append(str(exc));continue
                check(eid==owner,'exterior physical entity ID mismatch '+eid)
                if e['type']=='zone':
                    check(not b.get('buildingId'),'range must not acquire source building ID '+eid)
                    check(any(d['entityId']==eid and d['physicalDomainId']==b.get('physicalDomainId') for d in range_domains),'range has no matching original physical domain '+eid)
                    check(r.get('physicalDomainId')==b.get('physicalDomainId'),'range representation physical domain mismatch '+eid)
                    check(all(o.get('ownership')=='aggregate-source' for o in b['objects']),'official aggregate range must assign its complete source to the declared zone '+eid)
                check([x['id'] for x in r['objects']]==[x['id'] for x in b['objects']],'partial/reordered exterior bundle '+eid)
                for obj,src in zip(r['objects'],b['objects']):
                    check(obj['asset']=='/models/exteriors/'+src['url'],'object URL mismatch '+obj['id'])
                    for key in ('offset','matrix','bounds'):check(obj.get(key)==src.get(key),'object transform/bounds mismatch '+obj['id']+' '+key)
                    check(obj.get('ownership')==src.get('ownership'),'object ownership mismatch '+obj['id'])
                    check_model(obj['asset'],src.get('gltfSha256',src.get('sha256')))
                mask=r['mask'];check(mask['asset']=='/models/exteriors/'+b['mask']['url'],'mask asset mismatch')
                check(mask['exactAsset']=='/models/exteriors/'+b['mask']['exactUrl'],'exact mask asset mismatch')
                for key in ('boundsXZ','width','height','rowDirection','textureFlipY','heightMin','heightMax','metersPerPixel'):
                    check(mask[key]==b['mask'][key],'mask projection mismatch '+key)
                for key in ('asset','exactAsset'):
                    mp=exists(mask[key])
                    if mp and mp.is_file():
                        data=mp.read_bytes();check(data[:8]==b'\x89PNG\r\n\x1a\n','mask PNG header')
                        check(struct.unpack('>II',data[16:24])==(mask['width'],mask['height']),'mask pixel dimensions')
                        if key=='asset':check(hashlib.sha256(data).hexdigest()==mask['sha256'],'mask SHA')
                check(not any(x['asset'].startswith('/models/standalone/') for x in e['representations']),'duplicate standalone exterior '+eid)
        for stop in e.get('stops',[]):
            stop_count+=1;check(stop['floorId'] in entities,'stop floor target');rr=next((r for r in e['representations'] if r['id']==stop['representationId']),None)
            check(rr is not None,'stop representation target')
            if not rr:continue
            floorid=stop['sourceFloorId'];floor=room_floor_cache.get(floorid) or json.loads((public/'interiors'/f'{floorid}.json').read_text())
            check(rr['floorId']==stop['floorId'],'stop floor/representation mismatch')
            expected=[];zs=set()
            for pi in stop['partIndices']:
                part=floor['rooms'][pi];check(pi in rr['partIndices'],'stop part outside representation')
                check(part['sourceLocationId']==stop['locationId'],'stop location ID mismatch')
                expected.append([part['center'][0],part['heightSourceZ'],part['center'][1]])
                if part['heightSourceZ'] is not None:zs.add(part['heightSourceZ'])
            check(stop['position'] in expected,'invented stop position '+eid)
            check(set(stop['sourceZValues'])==zs,'stop source Z mismatch')
            check(stop.get('doorSide') is None and stop.get('doorPosition') is None,'unverified stop door metadata')
    for lid,owners in locations.items():check(len(owners)==1,'location ID ambiguity not declared '+lid)
    check(not set(locations).intersection(ambiguous),'ambiguous location also exposed as unique')
    im=json.loads((public/'interiors/manifest.json').read_text());expected=set()
    for f in im['floors']:
        floor=room_floor_cache.get(f['id']) or json.loads((public/'interiors'/f['url']).read_text())
        expected.update((f['id'],i) for i,r in enumerate(floor['rooms']) if r['interactive'])
    check(set(room_owners)==expected,'complete room part coverage');check(all(v==1 for v in room_owners.values()),'room part has multiple physical owners')
    check(len(mesh_entities)==len(bundles),'not every installed complete exterior bundle has one representation')
    for eid in set(mesh_entities):
        expected=[b for b in exterior['bundles'] if exterior_entity_id(b)==eid]
        entity=entities[eid];bound=[r for r in entity['representations'] if r['type']=='mesh_group']
        check({r['featureId'] for r in bound}=={b['id'] for b in expected},'exterior group lost or duplicated on shared entity '+eid)
        check(entity['externalIds'].get('exteriorBundleIds')==[b['id'] for b in expected],'exterior multi-group lookup mismatch '+eid)
        if len(expected)>1:check('exteriorBundleId' not in entity['externalIds'],'shared entity retains misleading single-bundle lookup '+eid)
    check(sum(len(b['objects']) for b in bundles.values())==sum(len(r['objects']) for e in entities.values() for r in e['representations'] if r['type']=='mesh_group'),'exterior source object and representation counts disagree')
    check(len(current_form_details)==registry['counts']['currentFormModels'],'current form count and validated model records disagree')
    check(len(sports_reps)==4 and len(outdoor['surfaceNodeEntityMap'])==4,'four original surface nodes')
    check(len(road_reps)==56,'fifty-six official street-code groups')
    check(sum(len(x['linesLocalXZ']) for x in outdoor['roads'])==223,'223 original centreline segments')
    check(len(outdoor['roadSourceMap'])==223,'original street centreline IDs unique')
    check(outdoor['counts']['cartographicBoundaryLinesAdded']==0,'cartographic boundary lines excluded')
    rids={r['resourceId'] for r in resources['resources']};check(len(rids)==len(resources['resources']),'duplicate resource ID')
    for r in resources['resources']:
        for b in r['bindings']:check(b['entityId'] in entities,'resource binding target')
        for asset in ([r['asset']] if r.get('asset') else list(r.get('faces',{}).values())):exists(asset)
    for edge in resources['links']:check(edge['from'] in rids and edge['to'] in rids,'resource edge endpoint')
    if ambiguous:warnings.append({'kind':'explicit-source-location-ambiguity','candidates':{k:sorted(v) for k,v in ambiguous.items()}})
    result={'status':'pass' if not errors else 'fail','errors':errors,'warnings':warnings,'counts':{'entities':len(entities),'representations':len(reps),'roomParts':len(room_owners),'exteriorBundles':len(mesh_entities),'exteriorSourceObjects':sum(len(b['objects']) for b in bundles.values()),'currentFormModels':len(current_form_details),'validatedModelObjects':len(gltf_checked),'checkedAssetFiles':len(checked_files),'connectorStops':stop_count,'sportsSurfaceEntities':len(sports_reps),'streetCodePaths':len(road_reps),'sourceStreetSegments':len(outdoor['roadSourceMap'])},'registry':str(registry_file),'project':str(project),'stagedExteriorOverride':str(exterior_file) if args.exteriors else None,'stagedSportsOverride':str(sports_file) if args.sports else None,'networkUsed':False,'currentForms':current_form_details}
    result['counts']['landmarkApproximationModels']=len(landmark_details);result['landmarks']=landmark_details
    text=json.dumps(result,ensure_ascii=False,indent=2)
    if args.report:args.report.write_text(text+'\n')
    print(text)
    if errors:raise SystemExit(1)

if __name__=='__main__':main()
