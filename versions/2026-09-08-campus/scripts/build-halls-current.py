#!/usr/bin/env python3
"""Evidence-labelled current facade approximation; no network or source-file mutation.
Use PYTHONPATH=/tmp/hkust-v3-deps Python3.12. Geometry source: saved official drawing
and terminal photogrammetry roof observations. Texture source: built-in image_gen.
"""
import argparse,hashlib,json,struct,math,importlib.util
from pathlib import Path
import numpy as np
from PIL import Image
from shapely.geometry import Polygon,LineString,Point,box
from shapely.ops import unary_union,split,triangulate
from shapely import contains_xy
from rasterio.features import rasterize
from affine import Affine

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def components(p):return [q for q in getattr(p,'geoms',[p]) if q.geom_type=='Polygon' and q.area>1e-5]
def parts(p):return [{'rings':[list(q.exterior.coords)]+[list(r.coords)for r in q.interiors]}for q in components(p)]

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--project',type=Path,default=Path('.'));ap.add_argument('--evidence',type=Path);ap.add_argument('--render',action='store_true');a=ap.parse_args();P=a.project.resolve();O=P/'public/models/current-forms/halls-current';E=a.evidence or O/'evidence'
 fps=json.loads((P/'public/data/building-footprints.json').read_text())['footprints'];fps={p['catalogId']:p for p in fps if p['catalogId']in['ug-hall-11','ug-hall-12','ug-hall-13']};fm=json.loads((P/'public/interiors/manifest.json').read_text());roof=np.load(E/'roof-grid.npz');top=roof['top'];yy,xx=np.mgrid[:top.shape[0],:top.shape[1]];px=float(roof['x0'])+(xx+.5)*float(roof['step']);pz=float(roof['z0'])+(yy+.5)*float(roof['step']);roof_source=json.loads((E/'geographic-audit.json').read_text())
 raw={k:unary_union([Polygon(q['rings'][0],q['rings'][1:]).buffer(0)for q in p['parts']])for k,p in fps.items()};envelopes={k:unary_union([Polygon(q.exterior)for q in components(v.buffer(.4,join_style=2).buffer(-.4,join_style=2))]).simplify(.18,preserve_topology=True)for k,v in raw.items()}
 overlap=envelopes['ug-hall-11'].intersection(envelopes['ug-hall-12']);envelopes['ug-hall-11']=envelopes['ug-hall-11'].difference(envelopes['ug-hall-12'])
 # Cross-sections follow observed terminal roof steps, not new building ownership.
 cuts={'ug-hall-11':[[[640,-1129],[730,-1117]]],'ug-hall-12':[[[680,-1089],[750,-1102]]],'ug-hall-13':[[[718,-1087],[790,-1130]],[[735,-1086],[790,-1077]]]}
 axes={'ug-hall-11':[[[664,-1105],[686,-1117]],[[688,-1123],[693,-1149]],[[687,-1115],[698,-1107]]],'ug-hall-12':[[[702,-1108],[713,-1101]],[[715,-1101],[726,-1105]],[[717,-1093],[719,-1073]],[[720,-1072],[732,-1064]]],'ug-hall-13':[[[752,-1133],[747,-1114]],[[732,-1107],[745,-1111]],[[748,-1107],[763,-1083]],[[764,-1078],[759,-1055]],[[760,-1052],[778,-1027]]]}
 texture_names=['courtyard-photo-derived.png','outer-photo-derived.png'];texinfo=[];images=[]
 for n in texture_names:
  p=O/'textures'/n;im=Image.open(p);im.verify();im=Image.open(p).convert('RGB');images.append(np.array(im));w,h=im.size;mi=0;u,v=w,h
  while True:
   mi+=4*u*v
   if u==v==1:break
   u=max(1,u//2);v=max(1,v//2)
  texinfo.append({'asset':'textures/'+n,'dimensions':[w,h],'bytes':p.stat().st_size,'sha256':sha(p),'baseRGBABytes':w*h*4,'rgbaWithMipBytes':mi,'method':'official-photo-reference built-in image_gen reconstruction; not untouched photographic pixels'})
 material=[{'name':'courtyard-blue-photo-derived','pbrMetallicRoughness':{'baseColorFactor':[1,1,1,1],'baseColorTexture':{'index':0},'metallicFactor':0,'roughnessFactor':.85},'doubleSided':True},{'name':'outer-pale-blue-photo-derived','pbrMetallicRoughness':{'baseColorFactor':[1,1,1,1],'baseColorTexture':{'index':1},'metallicFactor':0,'roughnessFactor':.85},'doubleSided':True}]
 for name,c,rough in [('pale-core-and-rounded-shade',[.8,.79,.73,1],.9),('roof-walkway',[.64,.63,.59,1],.95),('photovoltaic-dark-panel',[.065,.105,.17,1],.35),('panel-frame',[.63,.66,.68,1],.55),('core-vertical-dark-glazing',[.1,.17,.2,1],.4)]:material.append({'name':name,'pbrMetallicRoughness':{'baseColorFactor':c,'metallicFactor':0,'roughnessFactor':rough},'doubleSided':True})
 report=[];all_render=[]
 for key in ['ug-hall-11','ug-hall-12','ug-hall-13']:
  b=fps[key];env=envelopes[key];entity='building:'+b['officialBuildingId'];segments=components(env)
  for line in cuts[key]:
   segments=[r for p in segments for r in components(split(p,LineString(line)))]
  fit=[]
  for i,q in enumerate(segments):
   inside=contains_xy(q.buffer(-.65),px,pz)&np.isfinite(top)&(top>150)&(top<180);x=px[inside];z=pz[inside];h=top[inside];assert len(h)>20
   # RANSAC uses actual top intersections; selects a dominant flat/sloping roof surface.
   A=np.column_stack([x-q.centroid.x,z-q.centroid.y,np.ones(len(x))]);rng=np.random.default_rng(423+i);best=None
   for it in range(180):
    ids=rng.choice(len(x),3,replace=False)
    try:c=np.linalg.solve(A[ids],h[ids])
    except np.linalg.LinAlgError:continue
    if np.linalg.norm(c[:2])>.42:continue
    good=abs(A@c-h)<.38;score=int(good.sum())
    if best is None or score>best[0]:best=(score,good,c)
   assert best is not None
   c=np.linalg.lstsq(A[best[1]],h[best[1]],rcond=None)[0];rms=float(np.sqrt(np.mean((A[best[1]]@c-h[best[1]])**2)));fit.append({'part':q,'origin':[q.centroid.x,q.centroid.y],'coefficients':c,'sourceRoofSampleCount':len(h),'inliers':int(best[1].sum()),'rms':rms,'sourceMax':float(np.quantile(h,.99))})
  def roof_y(p):
   j=min(range(len(fit)),key=lambda i:fit[i]['part'].distance(Point(*p)));r=fit[j];v=np.array(p)-r['origin'];return float(v@r['coefficients'][:2]+r['coefficients'][2])
  meshes=[]
  def add(name,tri,mi,uv=None,extra=None):
   if not len(tri):return
   t=np.asarray(tri,dtype='<f4').reshape(-1,3,3);n=np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]);keep=np.linalg.norm(n,axis=1)>1e-7;t=t[keep];n=n[keep];n/=np.linalg.norm(n,axis=1)[:,None]
   u=None if uv is None else np.asarray(uv,dtype='<f4').reshape(-1,3,2)[keep];meshes.append((name,t,np.repeat(n[:,None,:],3,axis=1),mi,u,extra or{}))
  def patch(poly,height,mi,name):
   tr=[]
   for q in components(poly):
    for t in triangulate(q):
     if q.covers(t.representative_point()) and t.difference(q).area<1e-6:
      pts=list(t.exterior.coords)[:3];tr.append([[x,height([x,z]) if callable(height) else height,z]for x,z in pts])
   add(name,tr,mi)
  # Facade floor rhythm is appearance-only: preserve original source floors separately.
  base=133.95;pitch=3.15;walls=[[],[]];uvs=[[],[]];shade=[];allneighbours=unary_union([v for k,v in envelopes.items()if k!=key]);courtyard=np.array([713,-1077.])
  for q in components(env):
   pts=np.array(q.exterior.coords);counter=0.
   for s,e in zip(pts[:-1],pts[1:]):
    length=np.linalg.norm(e-s)
    if length<.03:continue
    middle=(s+e)/2
    if allneighbours.buffer(.06).contains(Point(*middle)):counter+=length;continue
    direction=(e-s)/length;normal=np.array([direction[1],-direction[0]]);probe=middle+normal*.2
    if env.contains(Point(*probe)):normal=-normal
    mi=0 if normal@(courtyard-middle)>0 else 1
    end_y=[roof_y(s),roof_y(e)];max_y=max(end_y);levels=[base]+[base+i*pitch for i in range(1,30)if base+i*pitch<max_y]+[max_y]
    for li,(lo,hi) in enumerate(zip(levels[:-1],levels[1:])):
     if hi-lo<.05:continue
     sh=min(hi,end_y[0]);eh=min(hi,end_y[1]);sl=min(lo,end_y[0]);el=min(lo,end_y[1]);p=[[s[0],sl,s[1]],[e[0],el,e[1]],[e[0],eh,e[1]],[s[0],sh,s[1]]]
     # Five complete rows from the generated texture; incomplete edge rows excluded.
     rows=[[20,180],[185,340],[348,500],[506,660],[665,815]] if mi==0 else [[40,214],[219,390],[395,568],[574,744],[750,920]];rt,rb=rows[li%5];u0=(counter/25)%1;u1=u0+length/25
     # Split long edges to keep UV within one observed material module, without repeating full photo context.
     breaks=[0.]+[(k*25-counter)/length for k in range(int(counter//25)+1,int((counter+length)//25)+1)if 1e-7<(k*25-counter)/length<1-1e-7]+[1.]
     for f0,f1 in zip(breaks[:-1],breaks[1:]):
      a0=np.array(p[0])*(1-f0)+np.array(p[1])*f0;a1=np.array(p[0])*(1-f1)+np.array(p[1])*f1;b0=np.array(p[3])*(1-f0)+np.array(p[2])*f0;b1=np.array(p[3])*(1-f1)+np.array(p[2])*f1;us=(f1-f0)*length/25;start=(counter/25+f0*length/25)%1.;start=0. if start>.999999 else start;vb=rb/1024;vt=rt/1024
      walls[mi].extend([[a0,a1,b1],[a0,b1,b0]]);uvs[mi].extend([[[start,vb],[start+us,vb],[start+us,vt]],[[start,vb],[start+us,vt],[start,vt]]])
    counter+=length
   # Thin rounded-return shade geometry follows true bent perimeter, no floor slab in the interior.
   for h in np.arange(base+pitch,base+40,pitch):
    for s,e in zip(pts[:-1],pts[1:]):
     mid=(s+e)/2
     if np.linalg.norm(e-s)<1 or h>min(roof_y(s),roof_y(e))-.5 or allneighbours.buffer(.06).contains(Point(*mid)):continue
     v=e-s;v/=np.linalg.norm(v);n=np.array([v[1],-v[0]])
     if env.contains(Point(*(mid+n*.15))):n=-n
     # A narrow 0.22 m projection is qualitative from photos, not a surveyed shade depth.
     p0=s+n*.01;p1=e+n*.01;p2=e+n*.22;p3=s+n*.22;shade.extend([[[p0[0],h,p0[1]],[p1[0],h,p1[1]],[p2[0],h+.08,p2[1]]],[[p0[0],h,p0[1]],[p2[0],h+.08,p2[1]],[p3[0],h+.08,p3[1]]]])
  for mi in range(2):add('photo-derived-courtyard'if mi==0 else'photo-derived-outer',walls[mi],mi,uvs[mi],{'geometryRole':'approximate_facade','windowRhythmMeasured':False})
  add('thin-perimeter-shading',shade,2,extra={'geometryRole':'photo_observed_shade_approximation','projectionMeters':.22,'measured':False})
  for i,r in enumerate(fit):
   fn=lambda p,r=r:float((np.array(p)-r['origin'])@r['coefficients'][:2]+r['coefficients'][2]);patch(r['part'],fn,3,'observed-roof-plane-'+str(i))
  pv_report=[]
  for ai,axis in enumerate(axes[key]):
   A,B=np.array(axis,float);v=B-A;length=np.linalg.norm(v);v/=length;n=np.array([-v[1],v[0]]);foot=Polygon([A+n*2.9,B+n*2.9,B-n*2.9,A-n*2.9]).intersection(env.buffer(-.7))
   if foot.area<10:continue
   # Photo-supported narrow tilted arrays; positions are aligned to source wing direction,
   # panel dimensions/spacing/tilt are explicit appearance parameters, not a PV survey.
   cap=np.nanquantile(top[contains_xy(foot,px,pz)&np.isfinite(top)],.99)
   # Photographs show long inclined canopies between the observed higher core
   # and lower roof, not an almost horizontal panel across every wing. Source
   # endpoint observations bound the appearance ramp; they are not survey Z.
   endpoints=[]
   for end in [A,B]:
    local=(np.hypot(px-end[0],pz-end[1])<3.5)&np.isfinite(top)&contains_xy(env,px,pz)
    observed=float(np.quantile(top[local],.85))if local.any()else roof_y(end)
    endpoints.append(max(roof_y(end)+.2,min(observed-.12,float(cap)-.08)))
   def py(p):
    along=float(np.clip((np.array(p)-A)@v/length,0,1));ramp=endpoints[0]*(1-along)+endpoints[1]*along
    # Never bury a panel beneath the regularized roof: the former min-only cap
    # caused sections of PV to disappear. The positive clearance is explicit.
    return max(roof_y(p)+.14,min(ramp,float(cap)-.08))
   canopy=foot.buffer(.22,join_style=2).intersection(env.buffer(-.4));patch(canopy,lambda p:py(p)-.07,2,'photo-observed-inclined-canopy-'+str(ai))
   patch(foot,py,4,'photo-observed-roof-pv-'+str(ai));pv_report.append({'axis':axis,'widthParameter':5.8,'heightEndpointSourceQuantile':.85,'sourceObservationRadiusMeters':3.5,'rampEndpointHeights':endpoints,'minimumClearanceAboveRegularizedRoof':.14,'actualSourceLocalCeiling':float(cap),'areaM2':foot.area,'placementIsApproximate':True})
   # Real panel-cell framing as narrow geometry strips, not painted fake source photography.
   for along in np.arange(0,length+.01,1.25):
    c=A+v*along;s=Polygon([c-v*.018+n*2.9,c+v*.018+n*2.9,c+v*.018-n*2.9,c-v*.018-n*2.9]).intersection(foot);patch(s,lambda p:py(p)+.012,5,'pv-frame-'+str(ai)+'-'+str(round(along,2)))
   c=(A+B)/2;s=Polygon([A+n*.02,B+n*.02,B-n*.02,A-n*.02]).intersection(foot);patch(s,lambda p:py(p)+.012,5,'pv-long-frame-'+str(ai))
  # Higher rectangular core ends are selected only from actual roof observations above the fitted roof.
  core_report=[]
  for ai,axis in enumerate(axes[key]):
   A,B=np.array(axis,float);v=B-A;v/=np.linalg.norm(v);n=np.array([-v[1],v[0]])
   for end in [A,B]:
    candidate=Polygon([end+v*2.5+n*4,end-v*2.5+n*4,end-v*2.5-n*4,end+v*2.5-n*4]).intersection(env)
    ix=contains_xy(candidate,px,pz)&np.isfinite(top);vals=top[ix]
    if len(vals)<12:continue
    core_y=float(np.quantile(vals,.85));roof_local=roof_y(end)
    if core_y-roof_local<1.0:continue
    # Two candidate ends may overlap; preserve one physical exterior core.
    if any(candidate.intersection(c['poly']).area>candidate.area*.2 for c in core_report):continue
    patch(candidate,core_y,2,'observed-tall-core-top-'+str(len(core_report)));wall=[]
    for q in components(candidate):
     for s,e in zip(list(q.exterior.coords)[:-1],list(q.exterior.coords)[1:]):
      wall.extend([[[s[0],base,s[1]],[e[0],base,e[1]],[e[0],core_y,e[1]]],[[s[0],base,s[1]],[e[0],core_y,e[1]],[s[0],core_y,s[1]]]])
    add('photo-observed-pale-core-'+str(len(core_report)),wall,2,extra={'role':'source-roof-high-point-and-photo-core-approximation','measuredFacade':False});core_report.append({'poly':candidate,'sourceYQuantile85':core_y,'sourceSampleCount':len(vals),'notSurveyedCoreBoundary':True})
  # Pack complete offline GLB. Every model owns its textures, referenced relative URLs are optional evidence only.
  g={'asset':{'version':'2.0','generator':'HKUST official-domain / observed source-roof / photo-derived current facade approximation'},'scene':0,'scenes':[{'nodes':[]}],'nodes':[],'meshes':[],'materials':material,'accessors':[],'bufferViews':[],'buffers':[{}],'images':[],'textures':[{'source':0,'sampler':0},{'source':1,'sampler':0}],'samplers':[{'magFilter':9729,'minFilter':9987,'wrapS':33071,'wrapT':33071}]};binary=bytearray()
  def bv(raw):
   binary.extend(b'\0'*((-len(binary))%4));i=len(g['bufferViews']);g['bufferViews'].append({'buffer':0,'byteOffset':len(binary),'byteLength':len(raw)});binary.extend(raw);return i
  def acc(v,kind):
   a=np.asarray(v,'<f4');i=len(g['accessors']);d={'bufferView':bv(a.tobytes()),'componentType':5126,'count':len(a),'type':kind}
   if kind=='VEC3':d.update(min=a.min(0).tolist(),max=a.max(0).tolist())
   g['accessors'].append(d);return i
  for name in texture_names:g['images'].append({'bufferView':bv((O/'textures'/name).read_bytes()),'mimeType':'image/png','name':name})
  for name,t,n,mi,u,extra in meshes:
   at={'POSITION':acc(t.reshape(-1,3),'VEC3'),'NORMAL':acc(n.reshape(-1,3),'VEC3')}
   if u is not None:at['TEXCOORD_0']=acc(u.reshape(-1,2),'VEC2')
   i=len(g['nodes']);g['scenes'][0]['nodes'].append(i);g['nodes'].append({'name':name,'mesh':i,'extras':{'entityId':entity,'buildingId':b['officialBuildingId'],'approximate':True,**extra}});g['meshes'].append({'primitives':[{'attributes':at,'mode':4,'material':mi}]});all_render.append((t,u,mi,mi if mi<2 else None))
  g['buffers'][0]['byteLength']=len(binary);g['extras']={'entityId':entity,'alreadyLocal':True,'sourceRoofHeightsArePhotogrammetricObservationsNotSurvey':True,'noNewFloorEntities':True,'wholeGroupHiddenWhenInteriorOpened':True};j=json.dumps(g,separators=(',',':')).encode();j+=b' '*((-len(j))%4);binary+=b'\0'*((-len(binary))%4);payload=struct.pack('<4sII',b'glTF',2,28+len(j)+len(binary))+struct.pack('<I4s',len(j),b'JSON')+j+struct.pack('<I4s',len(binary),b'BIN\0')+binary
  path=O/(key+'-current.glb');temp=path.with_suffix('.glb.tmp');temp.write_bytes(payload);temp.replace(path);verts=np.concatenate([m[1].reshape(-1,3)for m in meshes]);assert np.isfinite(verts).all();assert verts[:,1].max()<180
  xz=verts[:,[0,2]];mn=np.floor(xz.min(0)*2)/2;mx=np.ceil(xz.max(0)*2)/2;wh=((mx-mn)*2).astype(int);raster_shapes=[]
  for _,tt,_,_,_,_ in meshes:
   for tri in tt:
    poly=Polygon(tri[:,[0,2]])
    if poly.area>1e-8:raster_shapes.append((poly,255))
  mask=rasterize(raster_shapes,out_shape=(int(wh[1]),int(wh[0])),transform=Affine(.5,0,mn[0],0,.5,mn[1]),fill=0,dtype='uint8');mask_path=O/(key+'-projection.png');Image.fromarray(mask).save(mask_path);mask_info={'url':mask_path.name,'boundsXZ':{'min':mn.tolist(),'max':mx.tolist()},'width':int(wh[0]),'height':int(wh[1]),'pixelSizeMeters':.5,'heightMin':float(verts[:,1].min()),'heightMax':float(verts[:,1].max()),'sha256':sha(mask_path),'projection':'Actual final triangles at pixel centers; no bounding-box fill','activation':'Candidate old-source replacement mask only after this complete GLB is loaded; integration decides visibility'}
  floors=[f for f in fm['floors']if f['buildingId']==b['officialBuildingId']];r={'entityId':entity,'buildingId':b['officialBuildingId'],'catalogId':key,'name':b['catalogName'],'url':path.name,'sha256':sha(path),'bytes':len(payload),'bounds':{'min':verts.min(0).tolist(),'max':verts.max(0).tolist()},'triangles':sum(len(m[1])for m in meshes),'meshDefinitions':len(meshes),'textures':2,'textureRGBABytes':sum(t['baseRGBABytes']for t in texinfo),'textureRGBAWithMipBytes':sum(t['rgbaWithMipBytes']for t in texinfo),'sourceFloorZValues':sorted(set(z for f in floors for z in f['sourceZValues'])),'sourceFloors':[{'id':f['id'],'name':f['floorName'],'sourceZValues':f['sourceZValues'],'asset':'/interiors/'+f['url'],'sha256':sha(P/'public/interiors'/f['url'])}for f in floors],'envelopeParts':parts(env),'roofFits':[{'origin':f['origin'],'coefficients':f['coefficients'].tolist(),'inlierRMSMeters':f['rms'],'sourceRoofSampleCount':f['sourceRoofSampleCount'],'inliers':f['inliers'],'sourceY99':f['sourceMax'],'domain':parts(f['part'])}for f in fit],'pvApproximation':pv_report,'coreApproximation':[{k:v for k,v in c.items()if k!='poly'}|{'domain':parts(c['poly'])}for c in core_report],'runtime':{'alreadyLocal':True,'photoDerivedNeedsUnlit':True,'hideEntireGroupWhenOpenedBuildingId':b['officialBuildingId']},'mask':mask_info,'subtype':'official_domain_photo_source_roof_current_approximation'};report.append(r)
 manifest={'version':1,'checkedAt':'2026-09-06','type':'current_form_approximations','coordinateSystem':{'axes':'x=E-844800,y=source-local vertical,z=820500-N','alreadyLocal':True,'verticalDatum':'original photogrammetry local mapping; public floor Z kept unchanged as separate evidence'},'buildings':report,'appearanceTextures':texinfo,'sources':{'officialCompletedProject':'https://cdo.hkust.edu.hk/projects/jockey-club-i-village','officialCurrentPhotos':'https://hkust.edu.hk/news/hkust-hosts-opening-ceremony-jockey-club-i-village','officialIdentityMap':'https://publish.ust.hk/univ/maps/Campus_Map_Color.pdf','officialFootprints':{'asset':'/data/building-footprints.json','sha256':sha(P/'public/data/building-footprints.json')},'roofTerminalDescriptor':{'asset':'/models/hires/partial-residential-ias/manifest.json','sha256':sha(P/'public/models/hires/partial-residential-ias/manifest.json')},'roofSourceTiles':roof_source['photogrammetrySources'],'sourcePhotoAttributionAsset':'evidence/reference-manifest.json','promptAsset':'imagegen-prompts.json'},'parameters':{'facadeRhythmMeters':3.15,'rhythmMeaning':'appearance interpolation from public G/F133.95 and7/F156 difference divided by7, not evidence of unprovided floors','facadeDepthsMeasured':False,'drawingClosingDistanceMeters':.4,'drawingSimplifyToleranceMeters':.18,'roofPlanesMethod':'deterministic RANSAC of highest terminal-triangle vertical intersections,0.5m grid; per-terrace domains derived from observed roof steps','roofMeasured':False,'sourceDuplicateXIandXIIGroundDomainIntersectionM2':overlap.area,'duplicateDomainPolicy':'The overlapping XI ground drawing is assigned once to XII whose independent7/F footprint confirms the same building domain; stable floor data/entities are unchanged.'},'limitations':['Approximate current appearance, not as-built BIM or surveyed facade/roof.','Footprint bend geometry follows saved official drawing; closing and simplification are declared.','Only two source floors per hall are publicly saved; no new floor or room entities or Z values are invented.','Sparse PathAdvisor floor Z and photogrammetry roof surfaces have independent source limitations; floor source coordinates remain untouched.','Observed terminal roof heights constrain massing; terrace split, planar regularization, shading, core extent, PV geometry and materials are approximate.','The iB1000 roof177.6 belongs to a clipped aggregate feature spanning several halls and is not assigned to each hall.','Core and PV positions are source roof / photograph approximations, not surveyed installations.','Different courtyard and outside textures derive from actual official photographs using built-in image_gen; unknown side detail is approximate and is not untouched photographic imagery.','Copyright in official reference photos remains with HKUST / credited photographer Terence Pang Photography2026; no open source-photo license is asserted.','Do not count these three as original standalone high-resolution building bundles. Hide each entire update group when opening its interiors.']}
 temp=O/'manifest.json.tmp';temp.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n');temp.replace(O/'manifest.json');print(json.dumps([{k:b[k]for k in ['catalogId','triangles','meshDefinitions','bounds','bytes','sha256']}for b in report],indent=2))
 if a.render:
  spec=importlib.util.spec_from_file_location('innovation_renderer',P/'scripts/texture-innovation.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);v=np.concatenate([m[0].reshape(-1,3)for m in all_render]);center=(v.min(0)+v.max(0))/2;visual=[((t-center)*.42,u,mi,ti)for t,u,mi,ti in all_render];v=np.concatenate([m[0].reshape(-1,3)for m in visual]);mod.render_views(visual,material,images,v.min(0),v.max(0),O,label='HALLS XI-XIII / OFFICIAL DOMAIN + SOURCE ROOF + PHOTO-DERIVED APPROXIMATION / ')

if __name__=='__main__':main()
