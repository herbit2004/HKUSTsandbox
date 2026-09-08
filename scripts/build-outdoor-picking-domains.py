from pathlib import Path
import json,sys,importlib.util,hashlib
import numpy as np
from shapely import polygons
from shapely.geometry import Polygon,LineString,Point,box
from shapely.ops import unary_union,polygonize
P=Path(__file__).resolve().parents[1];sys.path.insert(0,str(P/'scripts'));from hkust_source_geometry import geometry
spec=importlib.util.spec_from_file_location('entrance',P/'scripts/build-entrance-surface.py');builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
root=Path('/tmp/hkust-v3-surfaces/gml/12-NW-6C/12-NW-6C/Layers');region=box(845000,821880,845250,822200);lines=[region.boundary]
for name in ['Transportation/CartoPedLine','Transportation/CartoTransLine','Buildings/Building']:
 for pr,arrays in builder.read_gml(root/(name+'.gml')):
  if not any(LineString(a[:,:2]).intersects(region)for a in arrays):continue
  for a in arrays:
   if name.startswith('Transportation')or(len(a)>3 and np.array_equal(a[0],a[-1])):lines.append(LineString(a[:,:2]))
faces=list(polygonize(unary_union(lines)));plaza=unary_union([faces[i]for i in [88,33,38,55]])
def parts(g):
 return [{'rings':[[[float(x-844800),float(820500-y)]for x,y in ring.coords]for ring in [poly.exterior,*poly.interiors]]}for poly in ([g]if g.geom_type=='Polygon'else g.geoms)]
plaza_parts=parts(plaza);q=Point(844800+331.073794,820500+1556.444185);assert plaza.contains(q)
m=json.load(open(P/'public/models/landmarks/sundial/manifest.json'));path=P/'public/models/landmarks/sundial'/m['url'];tri,_=geometry(path);proj=polygons(tri[:,:,[0,2]]);proj=[p for p in proj if p.area>1e-9];area=unary_union(proj);q2=Point(336.27203,-1549.63852)
print('redbird',area.contains(q2),area.distance(q2),'area',area.area,'bounds',area.bounds,'qYbounds',m['bounds'])
actual_area=area;area=area.buffer(.1,quad_segs=8)
localparts=[{'rings':[[[float(x),float(z)]for x,z in ring.coords]for ring in [poly.exterior,*poly.interiors]]}for poly in ([area]if area.geom_type=='Polygon'else area.geoms)]
out={'version':1,'groundSurfaces':[{'entityId':'outdoor_area:catalog:campus-61','parts':plaza_parts,'source':'Existing iB1000 exact polygonized entrance piazza face88 plus platform faces33/38/55, independently checked against source lines and official piazza photos. No road domains included.','sourceDomainIds':[88,33,38,55]}], 'sourceAssociations':[{'entityId':m['entityId'],'parts':localparts,'minY':m['bounds']['min'][1],'maxY':m['bounds']['max'][1],'roles':['baseline','photogrammetry','supplement'],'sourceAsset':'/models/landmarks/sundial/'+m['url'],'sourceSha256':hashlib.sha256(path.read_bytes()).hexdigest(),'method':'Old source photography within actual new sculpture projected triangles plus explicit 0.10m picking tolerance, and actual vertical extent; no rectangular ownership or skipped foreground.','pickingToleranceMeters':.1,'actualProjectionArea':actual_area.area}], 'qa':{'plazaPoint':[331.073794,121.988728,-1556.444185],'plazaPointInside':True,'plazaSourceArea':plaza.area,'sculpturePoint':[336.27203,124.25547,-1549.63852],'sculpturePointInsideActualProjection':actual_area.contains(q2),'distanceToActualProjectionMeters':actual_area.distance(q2),'sculpturePointInsidePickingTolerance':area.contains(q2),'sculptureProjectionArea':area.area,'sourceTriangles':len(tri)}}
f=P/'public/surfaces/entrance/entity-picking-domains.json';f.write_text(json.dumps(out,ensure_ascii=False,separators=(',',':'))+'\n');print('bytes',f.stat().st_size)
