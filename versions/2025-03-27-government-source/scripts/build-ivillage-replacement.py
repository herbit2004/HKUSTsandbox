#!/usr/bin/env python3
"""Bound the complete four-hall replacement by real source faces.

No ground, road, tree or portal geometry is generated here. A second atlas
preserves independently witnessed original ground surfaces at the replacement
edge. Original source files and their transforms remain untouched.
"""
import hashlib
import json
import argparse
import shutil
import io
import struct
from pathlib import Path

import numpy as np
import shapely
from affine import Affine
from PIL import Image
from rasterio.features import rasterize
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree
from shapely.geometry import Polygon
from shapely.ops import unary_union

P=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,default=P/'public/models/current-forms/ivillage-rebuild')
parser.add_argument('--source',type=Path,default=Path('/tmp/hkust-ivillage-rebuild-source'))
args=parser.parse_args()
I=P/'public/models/current-forms/ivillage-rebuild'
O=args.output.resolve();O.mkdir(parents=True,exist_ok=True);(O/'evidence').mkdir(exist_ok=True)
S=args.source
manifest=json.loads((I/'manifest.json').read_text())
evidence=json.loads((I/'evidence/geometry.json').read_text())
baseline_pixels=[np.asarray(Image.open(I/m['mask']['url']).convert('RGBA')).copy()for m in manifest['members']]
source=np.load(S/'terminal-triangles.npz')
T=source['positions'];N=source['normals'];C=T.mean(1)
source_tile_indices=source['sourceTileIndex'];source_triangle_indices=source['triangleIndex']
grid=np.load(S/'roof-grid.npz');h,w=grid['top'].shape
x0,z0,step=float(grid['x0']),float(grid['z0']),float(grid['step'])
rows,cols=np.indices((h,w));X=x0+(cols+.5)*step;Z=z0+(rows+.5)*step
transform=Affine(step,0,x0,0,step,z0)
envs=[unary_union([Polygon(p['rings'][0],p['rings'][1:])for p in b['envelopeParts']])for b in evidence['buildings']]
all_envs=unary_union(envs)
points=shapely.points(C[:,0],C[:,2])
dist=np.array([shapely.distance(e,points)for e in envs]);nearest=dist.argmin(0)
minimum=float(np.floor(min(m['bounds']['min'][1]for m in manifest['members'])-.25))
audit=[];union=np.zeros((h,w),bool)
member_pixels=[];assigned=np.zeros(len(T),bool)
source_rows=np.floor((C[:,2]-z0)/step).astype(int).clip(0,h-1)
source_cols=np.floor((C[:,0]-x0)/step).astype(int).clip(0,w-1)
terrain_at_source=grid['ground'][source_rows,source_cols]
# Do not grow a facade through its ground contact into roads or vegetation.
# This conservative exclusion is for attribution only; source ground remains
# independently preserved by the existing actual-intersection atlas below.
ground_contacts=(abs(C[:,1]-terrain_at_source)<=1)&(abs(N[:,1])>=.6)


def face_components(ids,edges_only=False):
    vertices=np.round(T[ids].reshape(-1,3)/.03).astype(np.int64)
    _,inverse=np.unique(vertices,axis=0,return_inverse=True)
    if edges_only:
        edges=np.sort(inverse.reshape(-1,3)[:,[[0,1],[1,2],[2,0]]].reshape(-1,2),axis=1)
        _,inverse=np.unique(edges,axis=0,return_inverse=True)
    order=np.argsort(inverse);iv=inverse[order];faces=np.repeat(np.arange(len(ids)),3)[order]
    shared=iv[1:]==iv[:-1];a,b=faces[:-1][shared],faces[1:][shared]
    graph=coo_matrix((np.ones(len(a)*2),(np.r_[a,b],np.r_[b,a])),shape=(len(ids),len(ids))).tocsr()
    return connected_components(graph,directed=False)


def witnesses(path,ids,**extra):
    np.savez_compressed(path,stagedTriangleIndex=ids,sourceTileIndex=source_tile_indices[ids],
        triangleIndex=source_triangle_indices[ids],**extra)


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def source_colours(ids):
    """Original photo samples, with glTF sampling and linear colour factors.

    These are appearance evidence, not semantic labels. Geometry/DTM below is
    mandatory before a connected patch can be excluded from wall attribution.
    """
    metadata=json.loads((S/'sources.json').read_text())['sources']
    rgb=np.full((len(T),3),np.nan);records=[]
    weights=np.array([[1,0,0],[0,1,0],[0,0,1],[1/3,1/3,1/3],
        [.6,.2,.2],[.2,.6,.2],[.2,.2,.6]])
    def wrap(q,mode):
        if mode==10497:return q%1
        if mode==33648:return 1-abs(q%2-1)
        if mode==33071:return np.clip(q,0,1)
        raise ValueError(f'Unsupported glTF sampler wrap {mode}')
    for si in np.unique(source_tile_indices[ids]):
        item=metadata[int(si)];raw=Path(item['localPath']).read_bytes()
        assert hashlib.sha256(raw).hexdigest()==item['sha256']
        size=struct.unpack_from('<I',raw,12)[0];g=json.loads(raw[20:20+size]);binary=raw[28+size:]
        def access(index):
            a=g['accessors'][index];v=g['bufferViews'][a['bufferView']]
            dt=np.dtype({5126:'<f4',5125:'<u4',5123:'<u2',5121:'u1'}[a['componentType']])
            k={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4}[a['type']]
            return np.ndarray((a['count'],k),dtype=dt,buffer=binary,
                offset=v.get('byteOffset',0)+a.get('byteOffset',0),strides=(v.get('byteStride',dt.itemsize*k),dt.itemsize))
        selected=ids[source_tile_indices[ids]==si];local=source_triangle_indices[selected]
        cursor=0;images={};samplers=[]
        def visit(index):
            nonlocal cursor
            node=g['nodes'][index]
            if 'mesh'in node:
                for pr in g['meshes'][node['mesh']]['primitives']:
                    attrs=pr['attributes'];ix=access(pr['indices']).reshape(-1).astype(int)if'indices'in pr else np.arange(g['accessors'][attrs['POSITION']]['count'])
                    ix=ix.reshape(-1,3);pick=np.flatnonzero((local>=cursor)&(local<cursor+len(ix)))
                    start=cursor;cursor+=len(ix)
                    if not len(pick):continue
                    mat=g.get('materials',[{}])[pr.get('material',0)].get('pbrMetallicRoughness',{})
                    factor=np.array(mat.get('baseColorFactor',[1,1,1,1]))[:3]
                    linear=np.broadcast_to(factor,(len(pick),len(weights),3)).copy()
                    if 'baseColorTexture'in mat:
                        desc=mat['baseColorTexture'];assert not desc.get('extensions'), 'Source UV transforms require explicit support'
                        tex=g['textures'][desc['index']];sampler=g.get('samplers',[])[tex['sampler']]if'sampler'in tex else{}
                        modes=[sampler.get('wrapS',10497),sampler.get('wrapT',10497)];samplers.append(modes)
                        image_index=tex['source']
                        if image_index not in images:
                            view=g['bufferViews'][g['images'][image_index]['bufferView']];offset=view.get('byteOffset',0)
                            image=np.asarray(Image.open(io.BytesIO(binary[offset:offset+view['byteLength']])).convert('RGB'))/255
                            images[image_index]=np.where(image<=.04045,image/12.92,((image+.055)/1.055)**2.4)
                        image=images[image_index]
                        uv=access(attrs[f"TEXCOORD_{desc.get('texCoord',0)}"])[ix[local[pick]-start]]
                        uv=np.einsum('nvc,sv->nsc',uv,weights)
                        # Wrap is evaluated at texel-centre coordinates as in a
                        # GL sampler, including bilinear taps across repeat seams.
                        u=wrap(uv[:,:,0],modes[0])*image.shape[1]-.5
                        v=wrap(uv[:,:,1],modes[1])*image.shape[0]-.5
                        x=np.floor(u).astype(int);y=np.floor(v).astype(int);fx=u-x;fy=v-y
                        def tap(a,b):
                            xx=np.floor(wrap((a+.5)/image.shape[1],modes[0])*image.shape[1]).astype(int).clip(0,image.shape[1]-1)
                            yy=np.floor(wrap((b+.5)/image.shape[0],modes[1])*image.shape[0]).astype(int).clip(0,image.shape[0]-1)
                            return image[yy,xx]
                        sampled=(tap(x,y)*(1-fx)[...,None]*(1-fy)[...,None]+tap(x+1,y)*fx[...,None]*(1-fy)[...,None]
                            +tap(x,y+1)*(1-fx)[...,None]*fy[...,None]+tap(x+1,y+1)*fx[...,None]*fy[...,None])
                        linear*=sampled
                    if 'COLOR_0'in attrs:raise ValueError('Source vertex colours require explicit composition')
                    srgb=np.where(linear<=.0031308,linear*12.92,1.055*np.maximum(linear,0)**(1/2.4)-.055)
                    rgb[selected[pick]]=np.mean(srgb,axis=1)
            for child in node.get('children',[]):visit(child)
        for root in g['scenes'][g.get('scene',0)]['nodes']:visit(root)
        assert np.isfinite(rgb[selected]).all()
        records.append({'sourceTileIndex':int(si),'sha256':item['sha256'],'localPath':item['localPath'],
            'sampledTriangles':len(selected),'samplerWrapModes':np.unique(samplers,axis=0).tolist()if samplers else[]})
    return rgb,records


# A shared source edge is not enough to identify a wall: the captured source
# joins trees/slope fragments to old scaffolding. Conservatively withhold squat,
# mixed-normal dark/cool patches near DTM. Tall strips and coherent planar walls
# fail the geometry gates even when their photo pixels are equally dark blue.
# These review thresholds are exclusion policy, not tree-species/land ownership.
colour_scope=np.flatnonzero((dist.min(0)<=8)&(T[:,:,1].max(1)>=minimum)&(T[:,:,1].min(1)<=181))
rgb,colour_sources=source_colours(colour_scope)
cool=(rgb.mean(1)<.43)&(rgb[:,1]>rgb[:,0]*1.12)&(rgb[:,2]>rgb[:,0]*1.1)


for bi,(member,record,env) in enumerate(zip(manifest['members'],evidence['buildings'],envs)):
    # Exact domain is regularized from official drawings. Beyond it only real,
    # connected source facade faces aligned with a drawing edge are candidates.
    boundary=env.boundary
    close=shapely.shortest_line(points,boundary)
    endpoints=shapely.get_point(close,1)
    dx=C[:,0]-shapely.get_x(endpoints);dz=C[:,2]-shapely.get_y(endpoints)
    length=np.maximum(np.hypot(dx,dz),1e-9)
    alignment=abs(N[:,0]*dx+N[:,2]*dz)/length
    upper=min(181,float(member['bounds']['max'][1])+.8)
    select=(nearest==bi)&(dist[bi]<=3)&(T[:,:,1].max(1)>=minimum)&(T[:,:,1].min(1)<=upper)
    select&=(dist[bi]<.65)|((abs(N[:,1])<.65)&(alignment>.7))
    ids=np.flatnonzero(select)
    count,component=face_components(ids)
    seed=dist[bi,ids]<.65
    keep=np.isin(component,np.unique(component[seed]));ids=ids[keep]
    initial_ids=ids.copy()
    # The radial face-normal filter above supplies conservative anchors, not a
    # classifier for every face of a warped old wall. Recover its edge-connected
    # sides before projecting the mask. The 8 m search bound is a review limit
    # (the witnessed XIII strip reaches 7.87 m), never a filled mask buffer.
    candidate=(nearest==bi)&(dist[bi]<=8)&(T[:,:,1].max(1)>=minimum)&(T[:,:,1].min(1)<=upper)
    candidate&=~ground_contacts
    # Find connected vertical shell support first. Short horizontal ledges can
    # join it, but may not grow attribution across a broad terrace/canopy merely
    # because that surface eventually shares an edge with a wall.
    vertical_candidate=candidate&((abs(N[:,1])<.8)|(dist[bi]<.65))
    vertical_ids=np.flatnonzero(vertical_candidate)
    _,vertical_components=face_components(vertical_ids,edges_only=True)
    vertical_attached=np.isin(vertical_components,np.unique(vertical_components[np.isin(vertical_ids,initial_ids)]))
    vertical_support_ids=vertical_ids[vertical_attached]
    support_shapes=[]
    for ix in vertical_support_ids:
        poly=Polygon(T[ix][:,[0,2]])
        support_shapes.append((poly.convex_hull.buffer(.251,join_style=2),1))
    support=rasterize(support_shapes,out_shape=(h,w),transform=transform,fill=0,dtype='uint8',all_touched=True)>0
    vertex_r=np.floor((T[:,:,2]-z0)/step).astype(int).clip(0,h-1)
    vertex_c=np.floor((T[:,:,0]-x0)/step).astype(int).clip(0,w-1)
    supported=support[source_rows,source_cols]&support[vertex_r,vertex_c].all(1)
    maximum_edge=np.linalg.norm(T-np.roll(T,1,axis=1),axis=2).max(1)
    short_ledge=supported&(maximum_edge<=2)
    candidate&=vertical_candidate|short_ledge
    candidate_ids=np.flatnonzero(candidate)
    wall_count,wall_component=face_components(candidate_ids,edges_only=True)
    anchored=np.isin(candidate_ids,initial_ids)
    attached=np.isin(wall_component,np.unique(wall_component[anchored]))
    additions=np.setdiff1d(candidate_ids[attached],initial_ids)
    rejected=candidate_ids[~attached]
    ids=np.union1d(initial_ids,additions)
    assigned[ids]=True
    component_audit=[]
    for ci in np.unique(wall_component[attached]):
        component_ids=candidate_ids[wall_component==ci]
        added_ids=np.intersect1d(component_ids,additions)
        if not len(added_ids):continue
        added_positions=T[added_ids].reshape(-1,3)
        component_audit.append({'component':int(ci),'addedTriangles':len(added_ids),
            'anchorTriangles':int(np.isin(component_ids,initial_ids).sum()),
            'bounds':{'min':added_positions.min(0).tolist(),'max':added_positions.max(0).tolist()},
            'maximumDistanceMeters':float(dist[bi,added_ids].max()),
            'facesNearSearchLimit':int((dist[bi,added_ids]>7.75).sum()),
            'sourceTileIndices':np.unique(source_tile_indices[added_ids]).tolist()})
    shapes=[]
    for ix in ids:
        t=T[ix];lo=max(minimum,float(t[:,1].min()))
        if lo>upper:continue
        poly=Polygon(t[:,[0,2]])
        if poly.area<1e-8:poly=poly.convex_hull
        # Half-pixel conservative support only around witnessed source faces.
        shapes.append((poly.buffer(.251,join_style=2),int(np.floor(lo))))
    alpha=rasterize(sorted(shapes,key=lambda p:-p[1]),out_shape=(h,w),transform=transform,
                    fill=0,dtype='uint8',all_touched=True)
    core=rasterize([(env,255)],out_shape=(h,w),transform=transform,fill=0,dtype='uint8',all_touched=True)
    occupied=(alpha>0)|(core>0)
    rgba=np.zeros((h,w,4),np.uint8);rgba[occupied,:3]=255
    rgba[alpha>0,3]=alpha[alpha>0];rgba[core>0,3]=255
    # Existing pixels are immutable lower-bound evidence. Newly admitted source
    # removal starts above the actual DTM's ground-adjacent volume, irrespective
    # of surface normal: a side slope must not disappear merely for being steep.
    previous=baseline_pixels[bi];previous_on=previous[:,:,0]>127
    previous_lower=np.where(previous[:,:,3]<255,np.maximum(minimum,previous[:,:,3]),minimum)
    proposed_lower=np.where(rgba[:,:,3]<255,np.maximum(minimum,rgba[:,:,3]),minimum)
    terrain_lower=np.ceil(grid['ground']+1)
    proposed_lower=np.maximum(proposed_lower,terrain_lower)
    proposed_on=occupied&np.isfinite(proposed_lower)&(proposed_lower<=upper)
    merged_lower=np.where(previous_on,np.minimum(previous_lower,np.where(proposed_on,proposed_lower,255)),proposed_lower)
    final_on=previous_on|proposed_on
    rgba[:]=0;rgba[final_on,:3]=255
    rgba[final_on,3]=np.where(merged_lower[final_on]>minimum,merged_lower[final_on],255).astype(np.uint8)
    member_pixels.append(rgba)
    member['mask']={'url':record['catalogId']+'-replacement.png',
        'boundsXZ':{'min':[x0,z0],'max':[x0+w*step,z0+h*step]},'width':w,'height':h,
        'pixelSizeMeters':step,'replacementMinY':minimum,'replacementMaxY':upper,
        'pixelMinYEncoding':'int-meters-alpha-255-common'}
    # Persistent face references let independent checks recover each projected
    # support face from the verified source preparation contract.
    witnesses(O/'evidence'/(record['catalogId']+'-replacement-witnesses.npz'),ids)
    witnesses(O/'evidence'/(record['catalogId']+'-added-wall-witnesses.npz'),additions)
    witnesses(O/'evidence'/(record['catalogId']+'-unattributed-candidates.npz'),rejected)
    audit.append({'catalogId':record['catalogId'],'sourceTriangles':len(ids),
        'occupiedPixels':int(occupied.sum()),'outsideEnvelopePixels':int(((alpha>0)&(core==0)).sum()),
        'candidateComponents':int(count),'seededComponents':int(len(np.unique(component[keep]))),
        'initialWitnessTriangles':len(initial_ids),'addedWallTriangles':len(additions),
        'unattributedCandidateTriangles':len(rejected),'edgeCandidateComponents':int(wall_count),
        'horizontalConnectionPolicy':'all vertices and centroid within witnessed vertical projection support; source triangle maximum edge <=2m',
        'maximumCandidateDistanceMeters':8,'initialAnchorDistanceMeters':3,'initialAnchorOutsideWallAlignment':.7,
        'edgeAttributionVertexToleranceMeters':.03,'addedComponents':component_audit,
        'distanceIsNotMaskFill':True,'replacementMinY':minimum,'replacementMaxY':upper})


def interval_union(images):
    lo=np.full((h,w),np.inf);hi=np.full((h,w),-np.inf)
    for member,pixels in zip(manifest['members'],images):
        on=pixels[:,:,0]>127
        lower=np.where(pixels[:,:,3]<255,np.maximum(minimum,pixels[:,:,3]),minimum)
        lo[on]=np.minimum(lo[on],lower[on]);hi[on]=np.maximum(hi[on],member['mask']['replacementMaxY'])
    return lo,hi


def clip_axis(poly,axis,bound,greater):
    out=[]
    for a,b in zip(poly,np.roll(poly,-1,axis=0)):
        da=(a[axis]-bound)*(1 if greater else -1);db=(b[axis]-bound)*(1 if greater else -1)
        if da>=-1e-10:out.append(a)
        if (da<0<db)or(db<0<da):out.append(a+(b-a)*(da/(da-db)))
    return np.asarray(out)


def cell_y_interval(triangle,row,col):
    poly=triangle
    for axis,bound,greater in [(0,x0+col*step,True),(0,x0+(col+1)*step,False),
            (2,z0+row*step,True),(2,z0+(row+1)*step,False)]:
        poly=clip_axis(poly,axis,bound,greater)
        if not len(poly):return None
    return float(poly[:,1].min()),float(poly[:,1].max())


# A 2.5D source mask cannot distinguish unrelated faces in the same column.
# Reject a new column if its gained vertical removal overlaps ANY unattributed
# source triangle. Clip in 3D to each actual half-metre cell so another face's
# distant vertex height cannot falsely stand in for this column's volume.
old_lo,old_hi=interval_union(baseline_pixels);new_lo,new_hi=interval_union(member_pixels)
# Classify only gained visible removal, so already hidden/in-shell geometry
# cannot bridge an actual detached canopy patch into a long building component.
# The independent regression evaluates the final result with real runtime masks.
new_center=(C[:,1]>=new_lo[source_rows,source_cols])&(C[:,1]<=new_hi[source_rows,source_cols])
old_center=(C[:,1]>=old_lo[source_rows,source_cols])&(C[:,1]<=old_hi[source_rows,source_cols])
dark_ids=np.flatnonzero(cool&assigned&new_center&~old_center&(dist.min(0)>.65))
_,dark_components=face_components(dark_ids)
nonbuilding_guard=np.zeros(len(T),bool);nonbuilding_records=[]
for ci in np.unique(dark_components):
    ids=dark_ids[dark_components==ci];positions=T[ids].reshape(-1,3)
    lo=positions.min(0);hi=positions.max(0);span=hi-lo
    area=np.linalg.norm(np.cross(T[ids,1]-T[ids,0],T[ids,2]-T[ids,0]),axis=1)/2
    if area.sum()<3:continue
    normal_moment=np.einsum('ni,nj,n->ij',N[ids],N[ids],area)/area.sum()
    planarity=float(np.linalg.eigvalsh(normal_moment).max())
    upright=float(np.average(abs(N[ids,1]),weights=area))
    delta=C[ids,1]-terrain_at_source[ids]
    squat=span[1]<=12 and span[1]<=1.2*np.hypot(span[0],span[2])
    near_ground=np.quantile(delta,.95)<=11
    # A squat oblique slope fragment may itself be planar. Only a coherent
    # VERTICAL plane supplies positive wall evidence here; do not force the
    # near-ground oblique fragment into a facade because it lacks rough normals.
    retain=squat and near_ground and upright>=.3 and (planarity<.84 or upright>=.45)
    record={'component':int(ci),'triangles':len(ids),'areaSquareMeters':float(area.sum()),
        'bounds':{'min':lo.tolist(),'max':hi.tolist()},'verticalToHorizontalAspect':float(span[1]/max(np.hypot(span[0],span[2]),1e-9)),
        'centroidMinusDTMRange':[float(delta.min()),float(delta.max())],
        'centroidMinusDTM95':float(np.quantile(delta,.95)),'normalMomentLargestEigenvalue':planarity,
        'areaWeightedAbsNormalY':upright,'meanSourceRGB':np.mean(rgb[ids],axis=0).tolist(),
        'withheldFromWallAttribution':bool(retain),'stagedTriangleIndices':ids.tolist()}
    nonbuilding_records.append(record)
    if retain:nonbuilding_guard[ids]=True
# Photo pixels vary within a canopy/slope fragment. Once the combined evidence
# withholds a component, include its connected brighter faces inside that same
# tightly bounded 3D fragment; do not leave holes at colour-threshold boundaries.
# This is only a SOURCE search box, never a painted/preserved rectangular mask.
for record in nonbuilding_records:
    if not record['withheldFromWallAttribution']:continue
    lo=np.array(record['bounds']['min'])-.75;hi=np.array(record['bounds']['max'])+.75
    local=np.flatnonzero(((C>=lo)&(C<=hi)).all(1)&(dist.min(0)>.65)&(C[:,1]-terrain_at_source<=12))
    _,parts=face_components(local)
    attached=np.isin(parts,np.unique(parts[np.isin(local,record['stagedTriangleIndices'])]))
    attached_ids=local[attached];nonbuilding_guard[attached_ids]=True
    record['connectedColourBoundarySourceTriangles']=len(attached_ids)
    record['connectedSourceSearchPaddingMeters']=.75
inherited_guard=I/'evidence/nonbuilding-source-witnesses.npz'
inherited_guard_count=0
if inherited_guard.exists():
    inherited_ids=np.load(inherited_guard)['stagedTriangleIndex']
    nonbuilding_guard[inherited_ids]=True;inherited_guard_count=len(inherited_ids)
guarded_ids=np.flatnonzero(nonbuilding_guard)
witnesses(O/'evidence/nonbuilding-source-witnesses.npz',guarded_ids,positions=T[guarded_ids],normals=N[guarded_ids],sourceRGB=rgb[guarded_ids])
(O/'evidence/nonbuilding-source-review.json').write_text(json.dumps({'policy':'Conservative non-building exclusion; colour AND squat connected geometry AND mixed normals AND proximity to real DTM. No universal foliage classifier.',
    'sampling':'Seven barycentric photo samples per triangle, glTF wrapS/wrapT with bilinear linear-RGB sampling and baseColorFactor, mean display RGB.',
    'sources':colour_sources,'components':nonbuilding_records,'guardedTriangles':len(guarded_ids),
    'inheritedVerifiedNonbuildingTriangles':inherited_guard_count,
    'inheritedGuardSHA256':digest(inherited_guard)if inherited_guard.exists()else None},indent=2)+'\n')

assigned[nonbuilding_guard]=False
for bi,member in enumerate(manifest['members']):
    path=O/'evidence'/(member['catalogId']+'-unattributed-candidates.npz')
    previous=np.load(path)['stagedTriangleIndex']
    withheld=guarded_ids[nearest[guarded_ids]==bi]
    witnesses(path,np.union1d(previous,withheld))
    audit[bi]['withheldNonBuildingSourceTriangles']=len(withheld)
    audit[bi]['postGuardAttributedSourceTriangles']=int((assigned&(nearest==bi)).sum())

# Adjacent terminal source tiles may retriangulate/quantize the SAME old wall.
# A small copied subtriangle can have no complete shared edge with its larger
# already attributed counterpart, and must not falsely block that entire column.
# Admit only a full three-vertex projection within 3 mm of ONE witnessed wall
# triangle and <=1 mm away from its plane, with aligned normals. This is source
# overlap evidence, not a nearest-building identity or a new spatial buffer.
overlap_refs=[]
overlap_anchors=np.flatnonzero(assigned&(abs(N[:,1])<.8))
tree=cKDTree(C[overlap_anchors])
overlap_candidates=np.flatnonzero(~assigned&~nonbuilding_guard&(dist.min(0)<=8)&
    (C[:,1]-terrain_at_source>1)&(C[:,1]>=minimum)&(C[:,1]<=181)&(abs(N[:,1])<.8)&
    (np.linalg.norm(T-np.roll(T,1,axis=1),axis=2).max(1)<=2))
near_dist,near_index=tree.query(C[overlap_candidates],k=32,distance_upper_bound=2)
for j,ds,indices in zip(overlap_candidates,near_dist,near_index):
    for d,index in zip(ds,indices):
        if not np.isfinite(d):continue
        anchor=int(overlap_anchors[index])
        if abs(N[j]@N[anchor])<.999:continue
        plane=np.abs((T[j]-T[anchor,0])@N[anchor])
        if plane.max()>.001:continue
        u=T[anchor,1]-T[anchor,0];u/=np.linalg.norm(u);v=np.cross(N[anchor],u)
        basis=np.column_stack([u,v]);outer=Polygon((T[anchor]-T[anchor,0])@basis)
        inner=Polygon((T[j]-T[anchor,0])@basis)
        if not outer.buffer(.003).covers(inner):continue
        assigned[j]=True
        overlap_refs.append({'stagedTriangleIndex':int(j),'witnessTriangleIndex':anchor,
            'sourceTileIndex':int(source_tile_indices[j]),'triangleIndex':int(source_triangle_indices[j]),
            'witnessSourceTileIndex':int(source_tile_indices[anchor]),'witnessSourceTriangleIndex':int(source_triangle_indices[anchor]),
            'maximumPlaneDistanceMeters':float(plane.max()),'absoluteNormalDot':float(abs(N[j]@N[anchor])),
            'projectedAreaSquareMeters':float(inner.area),'outsideWitnessAreaSquareMeters':float(inner.difference(outer).area)})
        break
overlap_ids=np.array([r['stagedTriangleIndex']for r in overlap_refs],dtype=np.int64)
witnesses(O/'evidence/overlapping-source-wall-witnesses.npz',overlap_ids,positions=T[overlap_ids],normals=N[overlap_ids],
    witnessTriangleIndex=np.array([r['witnessTriangleIndex']for r in overlap_refs],dtype=np.int64))
(O/'evidence/overlapping-source-wall-witnesses.json').write_text(json.dumps({'method':'Complete source triangle lies within 3mm of a witnessed wall triangle projection and <=1mm from its plane; normal dot>=.999. Single pass, no new region fill.',
    'triangles':len(overlap_refs),'faces':overlap_refs},indent=2)+'\n')
for bi,member in enumerate(manifest['members']):
    path=O/'evidence'/(member['catalogId']+'-unattributed-candidates.npz')
    witnesses(path,np.setdiff1d(np.load(path)['stagedTriangleIndex'],overlap_ids))
    audit[bi]['overlappingSourceCopiesProven']=int((nearest[overlap_ids]==bi).sum())
changed=(new_lo<old_lo)|(new_hi>old_hi)
integral=np.pad(changed.astype(np.int32),((1,0),(1,0))).cumsum(0).cumsum(1)
tl=T.min(1);th=T.max(1)
left=np.floor((tl[:,0]-x0-1e-9)/step).astype(int).clip(0,w-1)
right=np.floor((th[:,0]-x0+1e-9)/step).astype(int).clip(0,w-1)
top=np.floor((tl[:,2]-z0-1e-9)/step).astype(int).clip(0,h-1)
bottom=np.floor((th[:,2]-z0+1e-9)/step).astype(int).clip(0,h-1)
has_change=integral[bottom+1,right+1]-integral[top,right+1]-integral[bottom+1,left]+integral[top,left]
unknown_ids=np.flatnonzero(~assigned&(has_change>0)&(th[:,1]>=minimum)&(tl[:,1]<=max(m['mask']['replacementMaxY']for m in manifest['members'])))
witnesses(O/'evidence/unattributed-volumes-examined.npz',unknown_ids)
conflict=np.zeros((h,w),bool);conflict_refs=[];checked_columns=0
for ix in unknown_ids:
    rr,cc=np.nonzero(changed[top[ix]:bottom[ix]+1,left[ix]:right[ix]+1])
    for row,col in zip(rr+top[ix],cc+left[ix]):
        interval=cell_y_interval(T[ix],int(row),int(col))
        if interval is None:continue
        checked_columns+=1;low,high=interval
        nl,nh,ol,oh=new_lo[row,col],new_hi[row,col],old_lo[row,col],old_hi[row,col]
        # The old interval is continuous because every mask has the same common
        # floor and overlapping building height guards. Only gained removal is
        # tested; previously deleted source is not revived by this patch.
        lower_overlap=nl<ol and high>=nl and low<min(ol,nh)
        upper_overlap=nh>oh and high>max(oh,nl) and low<=nh
        if lower_overlap or upper_overlap:
            conflict[row,col]=True;conflict_refs.append((int(ix),int(row),int(col),low,high))
for bi,(member,pixels)in enumerate(zip(manifest['members'],member_pixels)):
    pixels[conflict]=baseline_pixels[bi][conflict]
    on=pixels[:,:,0]>127;union|=on
    path=O/member['mask']['url'];Image.fromarray(pixels).save(path)
    member['mask'].update(sha256=digest(path),bytes=path.stat().st_size)
    audit[bi]['occupiedPixels']=int(on.sum())
    audit[bi]['conservativeGroundAndConflictGuards']=True
conflict_array=np.asarray(conflict_refs,dtype=np.float64).reshape(-1,5)
conflict_ids=np.unique(conflict_array[:,0].astype(np.int64))
witnesses(O/'evidence/protected-unattributed-volumes.npz',conflict_ids,positions=T[conflict_ids],normals=N[conflict_ids],
    cellStagedTriangleIndex=conflict_array[:,0].astype(np.int64),row=conflict_array[:,1].astype(np.int32),
    col=conflict_array[:,2].astype(np.int32),cellMinY=conflict_array[:,3],cellMaxY=conflict_array[:,4])
np.savez_compressed(O/'evidence/column-guards.npz',oldMinY=old_lo,oldMaxY=old_hi,proposedMinY=new_lo,proposedMaxY=new_hi,
    finalMinY=interval_union(member_pixels)[0],finalMaxY=interval_union(member_pixels)[1],conflict=conflict,ground=grid['ground'],assignedSourceTriangles=assigned)
guard_report={'groundAdjacentVolumeMeters':1,'unknownTrianglesExamined':len(unknown_ids),
    'actualSourceColumnsExamined':checked_columns,'conflictingSourceTriangles':len(conflict_ids),
    'rejectedNewColumns':int(conflict.sum()),'retainedChangedColumns':int((changed&~conflict).sum()),
    'mode':'restore all original member pixels for every conflicting new source column; no extra sampler or preserved old shell interval',
    'faces':[{'stagedTriangleIndex':int(j),'sourceTileIndex':int(source_tile_indices[j]),'triangleIndex':int(source_triangle_indices[j]),
        'center':C[j].tolist(),'minY':float(tl[j,1]),'maxY':float(th[j,1]),'normal':N[j].tolist(),
        'dtm':float(terrain_at_source[j]),'centroidMinusDTM':float(C[j,1]-terrain_at_source[j]),'protectedFromNewDeletion':True}for j in conflict_ids]}
(O/'evidence/protected-unattributed-volumes.json').write_text(json.dumps(guard_report,indent=2)+'\n')

# Preserve only a true source-ground intersection outside the current shell.
# BA=255 means no old building preservation: X is rebuilt completely now.
matched=grid['groundMatched']
valid=union&np.isfinite(matched)&~shapely.contains_xy(all_envs,X,Z)
encoded=np.round(np.nan_to_num(matched)*256).astype(np.uint32)
protection=np.zeros((h,w,4),np.uint8);protection[:,:,2:]=255
protection[valid,0]=(encoded[valid]>>8).astype(np.uint8)
protection[valid,1]=(encoded[valid]&255).astype(np.uint8)
raw=O/'source-protection.rgba';raw.write_bytes(protection.tobytes())
Image.fromarray(protection).save(O/'source-protection.png')
protect={'url':raw.name,'sha256':digest(raw),'bytes':raw.stat().st_size,'width':w,'height':h,
    'boundsXZ':{'min':[x0,z0],'max':[x0+w*step,z0+h*step]},'pixelSizeMeters':step,
    'groundBandMeters':1,'groundPixels':int(valid.sum()),'structurePixels':0,
    'encoding':'rg-ground-uint16-256-ba-structure-int-255-absent',
    'source':'Actual terminal triangle vertical intersections, normal.y>=0.6, within 1m of the original terrain grid; full source indices recorded.',
    'activation':'Atomic with complete four-member model and all four checked replacement masks; old Hall X is no longer retained.'}
(O/'source-protection.json').write_text(json.dumps(protect,indent=2)+'\n')
manifest['sourceProtection']=protect
if O!=I.resolve():
    # A self-contained staging candidate retains the exact accepted GLB bytes.
    # Only its independently reviewed source-removal masks differ.
    shutil.copy2(I/manifest['asset']['url'],O/manifest['asset']['url'])
    if digest(O/manifest['asset']['url'])!=manifest['asset']['sha256']:
        raise RuntimeError('Current-form GLB changed during source-mask preparation; rerun against a stable input')
    shutil.copy2(I/'evidence/geometry.json',O/'evidence/geometry.json')
    before=O/'evidence/before';before.mkdir(exist_ok=True)
    before_manifest=json.loads((I/'manifest.json').read_text())
    for member in before_manifest['members']:
        shutil.copy2(I/member['mask']['url'],before/member['mask']['url'])
    shutil.copy2(I/before_manifest['sourceProtection']['url'],before/before_manifest['sourceProtection']['url'])
    shutil.copy2(I/'manifest.json',before/'manifest.json')
(O/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
rr,cc=np.nonzero(valid)
np.savez_compressed(O/'evidence/ground-preservation-witnesses.npz',row=rr,col=cc,height=matched[valid],
    sourceTileIndex=grid['groundSourceTileIndex'][valid],triangleIndex=grid['groundTriangleIndex'][valid])
(O/'evidence/replacement.json').write_text(json.dumps({'members':audit,'sourceProtection':protect,
    'sourcePreparationSHA256':digest(S/'source-preparation.json'),
    'conservativeColumnGuards':{k:v for k,v in guard_report.items()if k!='faces'},
    'nonBuildingSourceGuard':{'guardedSourceTriangles':len(guarded_ids),'evidence':'nonbuilding-source-review.json',
        'method':'Real-photo appearance plus squat DTM-near non-vertical connected geometry; connected colour-boundary faces retained as unknown source volume.',
        'rawWitnessFilesAreCandidatesBeforeThisGuard':True},
    'inputManifestSHA256':digest(I/'manifest.json') if O!=I.resolve() else None,
    'attribution':'Edge-connected non-ground source-wall expansion from the original conservative facade witnesses. No source surface is synthesized.',
    'limitations':['Connected facade attribution is a bounded visual correspondence, not a cadastral ownership survey.',
        'Components touching the 8m review boundary and remaining unanchored components require visual review; they are not silently expanded.',
        'No universal tree classifier is claimed. Ground contacts and unanchored edge components are excluded from new wall attribution.',
        'No newly synthesized ground patch or widened filled buffer is used to conceal a gap.',
        'Ground evidence is limited to actually intersected source faces; this check is not a replacement for live view inspection.']},indent=2)+'\n')
print(json.dumps({'members':audit,'groundPixels':protect['groundPixels'],'structurePixels':0},indent=2))
