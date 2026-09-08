"""Associate saved official named annotation anchors with their actual closed Building polygons.
No guessed point buffers, no new download, no generated rendered building geometry.
"""
from pathlib import Path
import json,hashlib,xml.etree.ElementTree as ET
from shapely.geometry import Polygon,Point
P=Path(__file__).resolve().parents[1];src=Path('/tmp/hkust-v3-surfaces/gml/12-NW-6C/12-NW-6C/Layers/Buildings');g='{http://www.opengis.net/gml}';f='{http://www.safe.com/gml/fme}'
MAPPINGS=[('campus-32','Tower A',['1101776553']),('campus-33','Tower B',['1101776428']),('campus-35','Global Graduate Tower',['1810202559','1810202562']),('ug-hall-3','Undergraduate Hall III',['1101775257']),('ug-hall-4','Undergraduate Hall IV',['1101775722']),('ug-hall-5','Postgraduate Hall II',['1101775411']),('ug-hall-7','Student Hall VII',['1101775401','1101763452'])]
reg=json.load(open(P/'public/data/entity-registry.json'));byid={e['entityId']:e for e in reg['entities']};features={};annotations={}
for member in ET.parse(src/'Building.gml').getroot().findall(g+'featureMember'):
 node=list(member)[0];pr={c.tag.split('}')[-1]:c.text for c in node if not list(c)};features[pr['BUILDINGID']]=(node,pr)
for member in ET.parse(src/'BuildingAnno.gml').getroot().findall(g+'featureMember'):
 node=list(member)[0];pr={c.tag.split('}')[-1]:c.text for c in node if not list(c)};annotations[pr['TextString']]=(node,pr)
raw=ET.Element(g+'FeatureCollection');out=[];decisions=[]
for legacy,label,ids in MAPPINGS:
 entity=byid[reg['legacyMap'][legacy]];anno,ap=annotations[label];n,e=map(float,anno.find('.//'+g+'pos').text.split());anchor=Point(e-844800,820500-n);raw.append(anno)
 for id in ids:
  node,pr=features[id];raw.append(node);parts=[]
  assert not node.findall('.//'+g+'ArcString')
  for patch in node.findall('.//'+g+'PolygonPatch'):
   rings=[]
   for tag in ['exterior','interior']:
    for ring in patch.findall(g+tag):
     value=list(map(float,ring.find('.//'+g+'posList').text.split()));rings.append([[value[i+1]-844800,820500-value[i]]for i in range(0,len(value),3)])
   if rings:
    polygon=Polygon(rings[0],rings[1:]);assert polygon.is_valid;assert polygon.contains(anchor) or polygon.distance(anchor)<1e-7;parts.append({'rings':rings})
  out.append({'entityId':entity['entityId'],'parts':parts,'boundaryToleranceMeters':.15,'minY':float(pr['BASELEVEL']),'maxY':float(pr['ROOFLEVEL']),'sourceBuildingId':id,'sourceProperties':pr,'annotation':{**ap,'localXZ':[anchor.x,anchor.y]},'method':'Existing official named BuildingAnno point lies inside this actual closed Building polygon; official campus alias links annotation name to canonical entity. P/T blocks kept separately with original base/roof levels. No area inferred from legacy reference point.'})
 decisions.append({'entityId':entity['entityId'],'name':entity['name'],'sourceLabel':label,'buildingIds':ids,'labelInsideEveryAssignedPolygon':True})
D=P/'public/data/picking';D.mkdir(exist_ok=True);ET.ElementTree(raw).write(D/'named-building-features.gml',encoding='utf-8',xml_declaration=True)
meta={'version':1,'domains':out,'decisions':decisions,'source':json.load(open('/tmp/hkust-v3-surfaces/manifest.json'))['sources'][0],'originalFiles':[{'name':name,'sha256':hashlib.sha256((src/name).read_bytes()).hexdigest()}for name in ['Building.gml','BuildingAnno.gml']],'heightMeaning':'Original iB1000 BASELEVEL/ROOFLEVEL metadata retained. Picking uses BASELEVEL minus0.5m only; ROOFLEVEL is not a hard ceiling because original UG V photography roof92.03m differs from iB roof88.1m. 0.15m edge hit tolerance does not alter source polygons; no generated visual extrusion.','coverage':{'canonicalBuildings':32,'previousOfficialBuildingDomains':18,'addedNamedOfficialBuildingDomains':7,'totalWithSourceDomain':25,'remaining':7},'remaining':'Medical and Daniel & Mayce Yu: construction with no current independent known form. President/Distinguished Guest/UniLodge: existing but no existing local georeferenced point or confirmed outline. UG VIII/IX: official saved annotation and Building polygon describe them together; no verified split into two building owners.'}
(D/'building-domains.json').write_text(json.dumps(meta,ensure_ascii=False,separators=(',',':'))+'\n');print(json.dumps({'domains':len(out),'buildingOwners':len(decisions),'bytes':(D/'building-domains.json').stat().st_size,'decisions':decisions},ensure_ascii=False))
