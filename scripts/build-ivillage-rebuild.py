#!/usr/bin/env python3
"""Rebuild all FOUR i-Village halls as one traceable representation set.

Offline, deterministic. Drawing domains + verified terminal source heights;
photograph-observed components have explicitly approximate dimensions. Public
floors and room data are never synthesized or modified by this script.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image
from shapely import contains_xy
from shapely.geometry import LineString, Point, Polygon, shape, mapping
from shapely.geometry.polygon import orient
from shapely.ops import split, unary_union

from ivillage_geometry import BuildingMesh, polygons, write_glb
from photo_materials import HallPhotoModules, prepare_photo, prepare_photo_patch


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def parts(geometry):
    return [{'rings': [list(p.exterior.coords), *[list(r.coords) for r in p.interiors]]}
            for p in polygons(geometry)]


# Cross-wing lines follow the abrupt changes visible in the terminal source
# height map. Their location is a regularization parameter, not a surveyed joint.
CUTS = {
    'ug-hall-10': [[[613, -1126], [615, -1105]], [[639, -1118], [624, -1096]],
                   [[622, -1083], [622, -1048]]],
    'ug-hall-11': [[[640, -1129], [730, -1117]]],
    'ug-hall-12': [[[680, -1089], [750, -1102]]],
    'ug-hall-13': [[[718, -1087], [790, -1130]], [[735, -1086], [790, -1077]],
                   [[758, -1029], [785, -1046]]],
}
# Centerlines are aligned to the independently saved drawing wings. These guide
# canopy/core detailing; they are not new road, bridge or floor entities.
AXES = {
    'ug-hall-10': [[[587,-1113],[608,-1115]], [[614,-1116],[630,-1114]],
                   [[630,-1114],[645,-1101]], [[648,-1097],[646,-1083]],
                   [[642,-1080],[624,-1073]], [[607,-1071],[616,-1054]],
                   [[650,-1097],[662,-1104]]],
    'ug-hall-11': [[[665,-1105],[686,-1117]], [[688,-1123],[693,-1149]],
                   [[687,-1116],[699,-1108]], [[694,-1150],[701,-1156]]],
    'ug-hall-12': [[[703,-1108],[713,-1101]], [[715,-1101],[726,-1105]],
                   [[717,-1093],[719,-1073]], [[720,-1072],[732,-1064]]],
    'ug-hall-13': [[[752,-1133],[747,-1114]], [[732,-1107],[745,-1111]],
                   [[748,-1107],[763,-1083]], [[764,-1078],[759,-1055]],
                   [[760,-1052],[771,-1037]], [[773,-1034],[779,-1026]]],
}
CORE_ANCHORS = {
    'ug-hall-10': [[586,-1113],[609,-1115],[637,-1107],[646,-1083],[617,-1051]],
    'ug-hall-11': [[665,-1106],[690,-1133],[701,-1156],[700,-1107]],
    'ug-hall-12': [[718,-1087],[732,-1063]],
    'ug-hall-13': [[753,-1101],[764,-1070],[773,-1037]],
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', type=Path, default=Path('/tmp/hkust-ivillage-rebuild-source'))
    parser.add_argument('--output', type=Path, default=Path('public/models/current-forms/ivillage-rebuild'))
    parser.add_argument('--photo-appearance', action='store_true', help='Use original official photo pixels with explicit facade module registration')
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=True)
    evidence = out/'evidence'; evidence.mkdir(exist_ok=True)
    photo_modules = HallPhotoModules() if args.photo_appearance else None
    texture_path = out/'textures/blue-ceramic-v1.png'
    photo_record = None
    paving_path = None
    if photo_modules:
        texture_path = out/'textures/official-facade-photo.jpg'
        photo_record = prepare_photo('/tmp/hkust-halls-11-13-references/news-Photo 6_0.jpg', texture_path,
            'https://hkust.edu.hk/sites/default/files/news/30844/Photo%206_0.jpg')
        photo_modules.save(evidence/'photo-registration.json', photo_record)
        paving_path = out/'textures/official-roof-paving.png'
        paving_record = prepare_photo_patch('/tmp/hkust-halls-11-13-references/cdo-098.HKUST-iVillage_Photos-DJI_0001-Pano_LR.jpg',
            paving_path,'https://cdo.hkust.edu.hk/sites/default/files/2026-07/098.HKUST-iVillage_Photos-DJI_0001-Pano_LR.jpg',
            [[990,1202],[1105,1245],[1050,1310],[935,1260]],1819)
        (evidence/'paving-registration.json').write_text(json.dumps(paving_record,indent=2)+'\n')
    grid = np.load(args.stage/'roof-grid.npz')
    top, ground = grid['top'], grid['ground']
    z0, x0, step = float(grid['z0']), float(grid['x0']), float(grid['step'])
    rows, cols = np.indices(top.shape)
    px, pz = x0+(cols+.5)*step, z0+(rows+.5)*step
    source_features = json.loads((args.stage/'normalized-envelopes.geojson').read_text())['features']
    metadata = {f['properties']['catalogId']:f['properties'] for f in source_features}
    original = {f['properties']['catalogId']:shape(f['geometry']) for f in source_features}
    envelopes = {k:v.simplify(.45, preserve_topology=True) for k,v in original.items()}
    # XI's base map includes the XII G/F fragment. XII's independent 7/F plan
    # resolves the physical exterior once. The original G/F records stay intact.
    duplicate = envelopes['ug-hall-11'].intersection(envelopes['ug-hall-12'])
    envelopes['ug-hall-11'] = unary_union(polygons(envelopes['ug-hall-11'].difference(envelopes['ug-hall-12'])))
    # At the X/XI join, prefer the X domain, avoiding a double wall / ownership.
    x_join = envelopes['ug-hall-11'].intersection(envelopes['ug-hall-10'])
    resolved_xi = envelopes['ug-hall-11'].difference(envelopes['ug-hall-10'])
    duplicate_residue = sum(p.area for p in polygons(resolved_xi) if p.area < 5)
    envelopes['ug-hall-11'] = unary_union([p for p in polygons(resolved_xi) if p.area >= 5])
    xii_join = envelopes['ug-hall-13'].intersection(envelopes['ug-hall-12'])
    envelopes['ug-hall-13'] = envelopes['ug-hall-13'].difference(envelopes['ug-hall-12'])
    all_envelopes = unary_union(list(envelopes.values()))
    floor_manifest = json.loads((project/'public/interiors/manifest.json').read_text())

    def ground_at(x,z):
        c = int(np.clip(np.floor((x-x0)/step),0,ground.shape[1]-1))
        r = int(np.clip(np.floor((z-z0)/step),0,ground.shape[0]-1))
        return float(ground[r,c])

    def observed(domain, quantile=.85):
        ids = contains_xy(domain, px,pz)&np.isfinite(top)&(top>150)&(top<181)
        return (float(np.quantile(top[ids],quantile)),int(ids.sum())) if ids.any() else (None,0)

    meshes, records = [], []
    for index,(key,env) in enumerate(envelopes.items()):
        b = metadata[key]; entity_id = 'building:'+b['officialBuildingId']
        mesh = BuildingMesh(entity_id,b['officialBuildingId'],key,photo_modules=photo_modules)
        domains = polygons(env)
        for cut in CUTS[key]:
            domains = [q for p in domains for q in polygons(split(p,LineString(cut)))]
        fits = []
        for i,domain in enumerate(domains):
            mask = contains_xy(domain.buffer(-.6),px,pz)&np.isfinite(top)&(top>150)&(top<181)
            x,z,h = px[mask],pz[mask],top[mask]
            if len(h)<20:
                mask = contains_xy(domain,px,pz)&np.isfinite(top)&(top>150)&(top<181)
                x,z,h = px[mask],pz[mask],top[mask]
            if len(h)<12:
                raise ValueError(f'{key} terrace {i} has insufficient source support: {len(h)}')
            origin=np.array([domain.centroid.x,domain.centroid.y])
            A=np.column_stack([x-origin[0],z-origin[1],np.ones(len(x))])
            rng=np.random.default_rng(934+index*100+i);best=None
            for _ in range(260):
                ix=rng.choice(len(h),3,replace=False)
                try:c=np.linalg.solve(A[ix],h[ix])
                except np.linalg.LinAlgError:continue
                if np.linalg.norm(c[:2])>.22:continue
                inliers=abs(A@c-h)<.33
                if best is None or inliers.sum()>best.sum():best=inliers
            if best is None or best.sum()<12:raise ValueError('No supported roof plane')
            c=np.linalg.lstsq(A[best],h[best],rcond=None)[0]
            fn=lambda x,z,c=c,o=origin:float(np.array([x-o[0],z-o[1],1])@c)
            fits.append({'domain':domain,'origin':origin.tolist(),'coefficients':c.tolist(),
                'height':fn,'samples':len(h),'inliers':int(best.sum()),
                'inlierRMSMeters':float(np.sqrt(np.mean((A[best]@c-h[best])**2)))})

        def roof_at(x,z):
            p=Point(x,z);f=min(fits,key=lambda f:f['domain'].distance(p))
            return f['height'](x,z)

        base=133.95
        neighbours=unary_union([v for k,v in envelopes.items() if k!=key])
        roof_detail=[];cores=[]
        # Photo-observed narrow pale towers at source height discontinuities.
        for anchor in CORE_ANCHORS[key]:
            a=np.array(anchor,dtype=float)
            axis=min(AXES[key],key=lambda s:LineString(s).distance(Point(*a)))
            v=np.subtract(axis[1],axis[0]).astype(float);v/=np.linalg.norm(v)
            n=np.array([-v[1],v[0]])
            candidate=Polygon([a+v*2.4+n*5,a-v*2.4+n*5,a-v*2.4-n*5,a+v*2.4-n*5])
            candidate=candidate.buffer(-.45,join_style=2).buffer(.45,quad_segs=4).intersection(env)
            height,count=observed(candidate,.88)
            if height is None or count<12:continue
            height=max(height,roof_at(*a)+.55)
            # A low roof mechanical cap is still recorded, rather than forcing
            # every candidate to be a fabricated extra full storey.
            cores.append({'domain':candidate,'height':height,'samples':count,'anchor':anchor})
        core_union=unary_union([c['domain'] for c in cores])

        for fi,fit in enumerate(fits):
            domain=fit['domain'];roof=fit['height']
            mesh.surface(domain,roof,2,'source-supported-roof-deck')
            for poly in polygons(domain):
                poly=orient(poly,sign=-1)
                for ring in [poly.exterior,*poly.interiors]:
                    points=np.asarray(ring.coords)
                    for a,bp in zip(points,points[1:]):
                        mid=(a+bp)/2;line=LineString([a,bp])
                        if env.boundary.distance(Point(*mid))>.025:
                            # One riser between differing terrace elevations.
                            others=[f for f in fits if f is not fit and f['domain'].distance(Point(*mid))<.02]
                            if others and roof(*mid)>others[0]['height'](*mid)+.08:
                                mesh.wall(a,bp,others[0]['height'],roof,1,'terrace-riser')
                            continue
                        if neighbours.buffer(.06).contains(Point(*mid)):continue
                        v=bp-a;length=np.linalg.norm(v)
                        if length<.02:continue
                        v/=length;normal=np.array([-v[1],v[0]])
                        # Split the actual boundary at pale-core intersections;
                        # opaque blue wall never runs through a core's outside.
                        visible=line.difference(core_union.buffer(.015))
                        for edge in getattr(visible,'geoms',[visible]):
                            if edge.geom_type!='LineString' or edge.length<.02:continue
                            q=np.asarray(edge.coords)
                            for s,e in zip(q,q[1:]):
                                if (e-s)@v<0:s,e=e,s
                                mesh.facade(s,e,base,roof,normal,ground_at=ground_at)
                                mesh.wall(s,e,lambda x,z:min(base,ground_at(x,z)-.5),base,10,'foundation-return')
                                mesh.wall(s,e,roof,lambda x,z:roof(x,z)+.65,11 if photo_modules else 0,'blue-roof-parapet')
                                cap=LineString([s,e]).buffer(.11,cap_style=2)
                                mesh.surface(cap,lambda x,z:roof(x,z)+.67,1,'parapet-coping')
                        # A continuous glass roof-edge walkway rail is offset
                        # inside the parapet; material opaque to avoid draw-order
                        # flicker against existing photogrammetry.
                        if length>3:
                            s=a-normal*.8;e=bp-normal*.8
                            if core_union.distance(Point(*(s+e)/2))>.15:
                                mesh.wall(s,e,lambda x,z:roof(x,z)+.68,lambda x,z:roof(x,z)+1.03,9,'roof-walkway-rail')
                                for u in np.arange(0,length,1.6):
                                    p=s+v*u;q=p+v*.045
                                    mesh.wall(p,q,roof,lambda x,z:roof(x,z)+1.04,8,'rail-post')

        for ci,core in enumerate(cores):
            for p in polygons(core['domain']):
                p=orient(p,sign=-1)
                mesh.solid(p,base,core['height'],1,'pale-vertical-core')
                # Narrow dark vertical glazing strip on the long exposed faces.
                for s,e in zip(list(p.exterior.coords),list(p.exterior.coords)[1:]):
                    s,e=np.array(s),np.array(e);v=e-s;length=np.linalg.norm(v)
                    if length<3:continue
                    v/=length;n=np.array([-v[1],v[0]]);mid=(s+e)/2
                    if env.boundary.distance(Point(*mid))>.25:continue
                    lo=max(base+.4,ground_at(*mid)+.15);hi=core['height']-1.6
                    if hi>lo:mesh.wall(mid-v*.3+n*.025,mid+v*.3+n*.025,lo,hi,3,'core-vertical-glazing')
                rim=p.difference(p.buffer(-.3))
                mesh.solid(rim,core['height'],core['height']+.32,1,'core-top-rim')

        for ai,axis in enumerate(AXES[key]):
            a,bp=np.asarray(axis,float);v=bp-a;length=np.linalg.norm(v);v/=length;n=np.array([-v[1],v[0]])
            # Split at source-supported terrace domains so canopies do not
            # bridge unrelated heights with an arbitrary full-length plane.
            outline=Polygon([a+n*2.7,bp+n*2.7,bp-n*2.7,a-n*2.7]).intersection(env.buffer(-.6))
            for fit in fits:
                foot=outline.intersection(fit['domain']).difference(core_union.buffer(.18))
                if foot.area<8:continue
                roof=fit['height']
                endpoint=[]
                for end in [a,bp]:
                    value,count=observed(Point(*end).buffer(3).intersection(env),.85)
                    endpoint.append(max(roof(*end)+.45,min(value if value else roof(*end)+.45,roof(*end)+3.0)))
                def canopy(x,z,a=a,v=v,L=length,h=endpoint,roof=roof):
                    t=np.clip((np.array([x,z])-a)@v/L,0,1)
                    return max(roof(x,z)+.38,float(h[0]*(1-t)+h[1]*t))
                mesh.surface(foot.buffer(.15,join_style=2).intersection(env.buffer(-.4)),lambda x,z:canopy(x,z)-.08,1,'inclined-canopy-underlay')
                mesh.surface(foot,canopy,7,'photovoltaic-panels')
                for poly in polygons(foot):
                    for s,e in zip(list(poly.exterior.coords),list(poly.exterior.coords)[1:]):
                        mesh.wall(s,e,lambda x,z:canopy(x,z)-.15,canopy,1,'canopy-fascia')
                for u in np.arange(0,length+.01,1.15):
                    c=a+v*u
                    frame=Polygon([c-v*.018+n*2.7,c+v*.018+n*2.7,c+v*.018-n*2.7,c-v*.018-n*2.7]).intersection(foot)
                    mesh.surface(frame,lambda x,z:canopy(x,z)+.012,8,'pv-cross-frame')
                for offset in [-.9,.9]:
                    frame=LineString([a+n*offset,bp+n*offset]).buffer(.015,cap_style=2).intersection(foot)
                    mesh.surface(frame,lambda x,z:canopy(x,z)+.013,8,'pv-long-frame')
                roof_detail.append({'axis':axis,'areaM2':foot.area,'rampEndpoints':endpoint})

        meshes.append(mesh)
        floors=[f for f in floor_manifest['floors'] if f['buildingId']==b['officialBuildingId']]
        records.append({'catalogId':key,'entityId':entity_id,'buildingId':b['officialBuildingId'],
            'envelopeParts':parts(env),'normalizationSymmetricDifferenceM2':env.symmetric_difference(original[key]).area,
            'roofFits':[{k:v for k,v in f.items() if k not in ['height','domain']}|{'domain':parts(f['domain'])}for f in fits],
            'cores':[{k:v for k,v in c.items()if k!='domain'}|{'domain':parts(c['domain'])}for c in cores],
            'canopies':roof_detail,'publicFloors':[{'id':f['id'],'name':f['floorName'],'sourceZValues':f['sourceZValues']}for f in floors]})

    # Joined drawing domains do not imply equal roof heights. Close the actual
    # vertical step between two independently fitted neighbouring buildings.
    # A single member owns each joint; opening that member retains its neighbour.
    joint_closures=[]
    fitted_domains=[[unary_union([Polygon(p['rings'][0],p['rings'][1:])for p in f['domain']])for f in r['roofFits']]for r in records]
    def member_roof(index,x,z):
        nearest=min(range(len(fitted_domains[index])),key=lambda j:fitted_domains[index][j].distance(Point(x,z)))
        fit=records[index]['roofFits'][nearest];ox,oz=fit['origin'];a,b,c=fit['coefficients']
        return a*(x-ox)+b*(z-oz)+c
    for i,(key,env) in enumerate(envelopes.items()):
        for j,other in enumerate(envelopes.values()):
            if j<=i:continue
            shared=env.boundary.intersection(other.boundary)
            for line in getattr(shared,'geoms',[shared]):
                if line.geom_type!='LineString' or line.length<.001:continue
                for a,b in zip(list(line.coords),list(line.coords)[1:]):
                    low=lambda x,z,i=i,j=j:min(member_roof(i,x,z),member_roof(j,x,z))
                    high=lambda x,z,i=i,j=j:max(member_roof(i,x,z),member_roof(j,x,z))
                    if max(high(*a)-low(*a),high(*b)-low(*b))<.002:continue
                    meshes[i].wall(a,b,low,high,1,'cross-building-roof-step-closure')
                    joint_closures.append({'owner':key,'neighbour':records[j]['catalogId'],'segment':[a,b],
                        'lower':[low(*a),low(*b)],'upper':[high(*a),high(*b)]})

    provenance={'representationSet':'hkust-ivillage-x-xiii-v1','alreadyLocal':True,
        'method':'official drawing domains / terminal triangle roof planes / photo-observed component reconstruction',
        'appearanceApproximation':True,'noNewFloorOrRoomEntities':True,
        'sharedAppearance':True,'atomicCompleteSet':True,
        'sourceGeometrySHA256':sha(args.stage/'terminal-triangles.npz'),
        'sourcePreparationSHA256':sha(args.stage/'source-preparation.json')}
    if photo_record:provenance['photographicAppearance']=photo_record
    asset=write_glb(out/'ivillage-x-xiii-v1.glb',meshes,texture_path,provenance,photographic=bool(photo_modules),paving_path=paving_path)
    for member,record in zip(asset['members'],records):record.update(member)
    manifest={'version':1,'id':provenance['representationSet'],'asset':{k:asset[k]for k in ['url','sha256','bytes']},
        'members':[{k:r[k]for k in ['entityId','buildingId','nodeName','bounds','catalogId']}for r in records],
        'coordinateSystem':'x=E-844800; y=source-local vertical; z=820500-N; no runtime offset',
        'appearance':{'materials':11,'embeddedTextures':1,'generatedAlbedo':'textures/blue-ceramic-v1.png',
            'windowGeometry':'openings, 0.13m reveals, inset glazing, slim frames; 3.15m row rhythm is appearance only',
            'shadowMethod':'stable shared neutral vertex daylight; no camera-dependent material tier',
            'photographReference':'../halls-current/evidence/reference-manifest.json'},
        'evidence':'evidence/geometry.json','limitations':['Facade opening spacing, roof detailing, core boundaries and canopy dimensions are photograph-guided approximations, not an as-built survey.',
            'The source geometry predates some completed finishes; source roof surfaces constrain massing but do not certify every current roof detail.',
            'Public floor and room records are preserved verbatim; visible facade rows do not create additional indoor entities.']}
    if photo_record:
        manifest['appearance']={'materials':14,'embeddedTextures':2,
            'photographicTexture':'textures/official-facade-photo.jpg',
            'registration':'evidence/photo-registration.json','pavingRegistration':'evidence/paving-registration.json',
            'windowGeometry':'Existing openings/recesses retained; photo UV faces split at every bay/window control boundary.',
            'shadowMethod':'Original photographic reflection, tile gradient and shading retained; no additional facade daylight multiplier.',
            'photographReference':'https://hkust.edu.hk/news/hkust-hosts-opening-ceremony-jockey-club-i-village'}
        manifest['limitations'].extend(['Photographic modules are reused over unphotographed elevations; this is not a calibrated full-building camera projection.',
            'The branch-obscured lowest photographic row is excluded. Core and paving material families use inspected source patches; exact roof finishes and surrounding landscape reconstruction remain incomplete.'])
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    (evidence/'geometry.json').write_text(json.dumps({'provenance':provenance,'buildings':records,
        'duplicateXIandXIIDomainM2':duplicate.area,'XIandXJoinOverlapM2':x_join.area,
        'XIIandXIIIJoinOverlapM2':xii_join.area,
        'discardedDuplicateBoundaryResidueM2':duplicate_residue,
        'identityPolicy':'XII independent upper-floor envelope resolves the duplicated XI ground fragment. Shared X/XI and XII/XIII exterior junction pieces render once under the lower numeral, preserving the complete union. This exterior pick policy does not change public source floors or claim surveyed indoor ownership.',
        'terminalSources':str(args.stage/'sources.json'),'roofTerraceCuts':CUTS,'componentGuideAxes':AXES,
        'crossBuildingRoofStepClosures':joint_closures},ensure_ascii=False,indent=2)+'\n')
    # Small deterministic CPU-render input for geometry review, independent of
    # browser loading or picking. Saved arrays carry the same material partition.
    render={}
    for m in meshes:
        for mat,faces in m.faces.items():render[f'{m.name.replace(" ","_")}_{mat}']=np.array([f[0]for f in faces])
    np.savez_compressed(evidence/'render-triangles.npz',**render)
    print(json.dumps({'asset':manifest['asset'],'buildings':[{k:r[k]for k in ['catalogId','triangles','bounds']}for r in records],
        'sharedDrawPrimitives':asset['drawPrimitives']},indent=2))


if __name__=='__main__':main()
