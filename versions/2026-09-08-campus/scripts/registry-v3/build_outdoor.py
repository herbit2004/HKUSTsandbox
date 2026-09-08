#!/usr/bin/env python3
"""Incrementally add verified outdoor surfaces and official street centrelines; no network."""
import argparse,collections,copy,hashlib,json,math,re,struct
from pathlib import Path
OUT=Path(__file__).resolve().parent
PROJECT=Path(__file__).resolve().parents[2]
SOURCES=Path('/tmp/hkust-v3-surfaces')
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(name,d): (OUT/name).write_text(json.dumps(d,ensure_ascii=False,separators=(',',':'))+'\n')
def norm(s):return re.sub('[^a-z0-9]','',s.lower())
def repid(eid,kind,asset,fid):return 'rep:'+hashlib.sha256(json.dumps([eid,kind,asset,fid],separators=(',',':')).encode()).hexdigest()[:16]
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--registry',type=Path,default=PROJECT/'public/data/entity-registry.json');ap.add_argument('--sources',type=Path,default=SOURCES);a=ap.parse_args()
    original=read(a.registry);r=copy.deepcopy(original);entities={e['entityId']:e for e in r['entities']};before=set(entities)
    sm=a.sources/'orthophoto-surface/manifest.json';sports=read(sm);rp=a.sources/'roads-campus.geojson';roads=read(rp)
    assert roads['crs']['properties']['name']=='EPSG:2326'
    glb=a.sources/'orthophoto-surface'/sports['url'];raw=glb.read_bytes();length=struct.unpack_from('<I',raw,12)[0];gltf=json.loads(raw[20:20+length])
    nodes={n.get('extras',{}).get('entityId'):n for n in gltf['nodes']}
    campus='campus:hkust-cwb';stadium=r['legacyMap']['campus-52'];assert entities[stadium]['type']=='zone'
    sports_asset='/surfaces/sports/'+sports['url'];outdoor_asset='/data/outdoor-entities.json'
    query=(a.sources/'roads-query-url.txt').read_text().strip()
    r['sources']['sports-ground']={'asset':'/surfaces/sports/manifest.json','note':'Four explicit official sports polygons with 2019–2020 CEDD DTM heights and unchanged 2025-01-11 orthophoto; no invented surface offset.'}
    r['sources']['streetcentreline']={'asset':outdoor_asset,'url':query,'service':'https://portal.csdi.gov.hk/server/rest/services/common/landsd_rcd_1637310758814_80061/FeatureServer/0','note':'Official StreetCentrelineID/STREETCODE segmented source; query includes adjacent roads and returns whole intersecting segments. Not a routing network or deck height survey.'}
    def add_entity(e):
        assert e['entityId'] not in entities,'Duplicate physical outdoor ID'
        entities[e['entityId']]=e;r['entities'].append(e)
        if e['parentId']:
            entities[e['parentId']]['relations'].append({'type':'contains','targetId':e['entityId'],'evidence':e['sourceId']})
    delta={'version':1,'checkedAt':'2026-09-06','coordinateSystem':r['coordinateSystem'],'surfaceNodeEntityMap':{},'surfaces':[],'roads':[],'roadSourceMap':{},
      'heightPolicy':{'roadDisplay':'sample DTM at runtime as a ground reference only; skip vertices/segments without DTM coverage','roadSourceZ':None,'deckHeight':None,'roadNetwork':'source segments only; no inferred connectivity, width, pavement or turn restrictions','tunnelPolicy':'segments explicitly typed Tunnel are not ground-draped by default'},
      'sources':{'sports':{'manifest':'/surfaces/sports/manifest.json','sha256':sha(sm)},'roads':{'source':query,'sha256':sha(rp),'crs':'EPSG:2326','sourceFeatures':len(roads['features']),'queryEnvelopeWGS84':[114.254,22.328,114.272,22.344],'fullIntersectingSegmentsPreserved':True}},
      'limitations':['This index adds only four supplied surface nodes and official street centrelines. Carto boundary/step lines are excluded.',
      'New road groups with no established physical campus containment have parentId=null. This is source context, not a claim that every road is inside campus.',
      'West/east tennis labels describe supplied source geometry; no Court number or affiliation inferred.']}
    for f in sports['features']:
        sid=f['entityId'];eid='outdoor_area:ib1000:'+str(f['sourcePolygonId']);assert sid in nodes
        parent=stadium if f.get('campusId')=='campus-52' else campus
        function='soccer_field' if sid=='soccer-field' else 'track_and_infield_surface' if sid=='stadium-infield-and-track' else 'tennis_court'
        representation={'id':repid(eid,'mesh_surface',sports_asset,sid),'type':'mesh_surface','subtype':'orthophoto_dtm_surface','asset':sports_asset,'featureId':sid,'nodeName':nodes[sid]['name'],'sourceId':'sports-ground','bounds':f['meshBounds'],'heightMode':'source CEDD DTM HKPD surface','sourceZRange':[f['meshBounds']['min'][1],f['meshBounds']['max'][1]],'textureDate':f['textureDate'],'geometrySurveyDate':f['geometrySurveyDate'],'offset':[0,0,0]}
        e={'entityId':eid,'type':'outdoor_area','name':f['nameZh'],'aliases':[],'externalIds':{'iB1000PolygonId':str(f['sourcePolygonId']),'surfaceNodeId':sid},'parentId':parent,'function':function,'sourceId':'sports-ground','sourceZValues':[],'bounds':f['meshBounds'],'representations':[representation], 'relations':[],
          'notes':['Source mesh already uses local coordinates. Heights vary over the terrain; sourceZValues=[] does not mean zero height. Tennis court number not established.']}
        add_entity(e);delta['surfaceNodeEntityMap'][sid]=eid
        delta['surfaces'].append({'entityId':eid,'sourceEntityId':sid,'nodeName':nodes[sid]['name'],'asset':sports_asset,'sourcePolygonId':str(f['sourcePolygonId']),'parentId':parent,'name':f['nameZh'],'bounds':f['meshBounds'],'center':f['center'],'boundaryLocalXZ':f['sourceBoundary'],'triangles':f['triangles'],'sourceId':'sports-ground'})
    # Group by explicit STREETCODE, and require consistent source names. Never dissolve/route original segments.
    groups=collections.defaultdict(list)
    for f in roads['features']:
        assert f['geometry']['type']=='LineString' and len(f['geometry']['coordinates'])>=2
        p=f['properties'];assert 'STREETCENTRELINEID' in p and 'STREETCODE' in p
        groups[str(p['STREETCODE'])].append(f)
    names_to_existing={norm(name):e['entityId'] for e in original['entities'] if e['type']=='path' for name in [e['name']]+e['aliases']}
    reused=[];conflicts=[];tunnel_count=0;max_roundoff=0.;line_count=0;sourceids=set()
    for code,features in sorted(groups.items()):
        en=sorted({f['properties']['ENGLISHSTREETNAME'] for f in features if f['properties']['ENGLISHSTREETNAME']});zh=sorted({f['properties']['CHINESESTREETNAME'] for f in features if f['properties']['CHINESESTREETNAME']})
        assert len(en)<=1 and len(zh)<=1,('Conflicting official names for STREETCODE',code)
        matching=names_to_existing.get(norm(en[0])) if en else None
        eid=matching or 'path:streetcode:'+code
        if matching:
            e=entities[eid];reused.append({'streetCode':code,'entityId':eid,'officialName':en[0]})
        else:
            name=zh[0] if zh else en[0].title() if en else '官方未命名道路 · STREETCODE '+code
            e={'entityId':eid,'type':'path','name':name,'aliases':[],'externalIds':{},'parentId':None,'sourceId':'streetcentreline','sourceZValues':[],'representations':[],'relations':[],'identityStatus':'official street-code group; campus physical containment not established'}
            add_entity(e)
        assert e['type']=='path'
        e['aliases']=list(dict.fromkeys(e['aliases']+en+zh));e['externalIds']['officialStreetCode']=code
        e['externalIds']['officialStreetCentrelineIds']=[str(f['properties']['STREETCENTRELINEID']) for f in features]
        record={'entityId':eid,'streetCode':code,'name':e['name'],'officialEnglishName':en[0] if en else None,'officialChineseName':zh[0] if zh else None,'linesLocalXZ':[],'segments':[],'sourceId':'streetcentreline','sourceZ':None,'deckHeight':None}
        for i,f in enumerate(features):
            prop=f['properties'];sid=str(prop['STREETCENTRELINEID']);assert sid not in sourceids;sourceids.add(sid)
            points=[]
            for point in f['geometry']['coordinates']:
                assert len(point)==2 and all(math.isfinite(x) for x in point)
                x,z=point[0]-844800,820500-point[1];rounded=[round(x,4),round(z,4)];max_roundoff=max(max_roundoff,math.dist([x,z],rounded));points.append(rounded)
            record['linesLocalXZ'].append(points)
            is_tunnel=prop['STREETTYPE']=='Tunnel';tunnel_count+=is_tunnel;line_count+=1
            segment={'lineIndex':i,'sourceFeatureId':f['id'],'streetCentrelineId':sid,'objectId':prop['OBJECTID'],'streetType':prop['STREETTYPE'],'sourceLastUpdatedTimestampMs':prop['LASTUPDATEDATE'],'displayGroundReference':not is_tunnel,'deckHeight':None}
            record['segments'].append(segment)
            delta['roadSourceMap'][sid]={'entityId':eid,'streetCode':code,'lineIndex':i,'sourceFeatureId':f['id'],'objectId':prop['OBJECTID']}
        bounds={'min':[min(p[0] for line in record['linesLocalXZ'] for p in line),min(p[1] for line in record['linesLocalXZ'] for p in line)],'max':[max(p[0] for line in record['linesLocalXZ'] for p in line),max(p[1] for line in record['linesLocalXZ'] for p in line)]}
        record['boundsXZ']=bounds;delta['roads'].append(record)
        e['representations'].append({'id':repid(eid,'line_group',outdoor_asset,code),'type':'line_group','subtype':'official_streetcentreline','asset':outdoor_asset,'featureId':code,'sourceId':'streetcentreline','boundsXZ':bounds,'heightMode':'runtime DTM ground reference only; source road/deck height unknown','sourceZ':None,'deckHeight':None})
    # Structural + additive checks, independent of the source registry builder.
    errors=[]
    def check(ok,msg):
        if not ok:errors.append(msg)
    check(original['legacyMap']==r['legacyMap'],'legacy map unchanged');check(before<=set(entities),'no old entity removed')
    check(len(entities)==len(r['entities']),'unique entity ID')
    oldtypes={e['entityId']:e['type'] for e in original['entities']};check(all(entities[eid]['type']==typ for eid,typ in oldtypes.items()),'old physical type unchanged')
    for e in r['entities']:
        check(e['parentId'] is None or e['parentId'] in entities,'parent reference')
        for rel in e['relations']:check(rel['targetId'] in entities,'relation target')
    check(len(delta['surfaces'])==4,'exactly four supplied surfaces');check(len(delta['surfaceNodeEntityMap'])==4,'surface node mapping unique')
    check(line_count==len(roads['features'])==223,'all source street centreline segments preserved');check(len(sourceids)==223,'source centreline identity unique')
    check(all(s['deckHeight'] is None for p in delta['roads'] for s in p['segments']),'deck height not invented')
    check(not conflicts,'no inconsistent name/code grouping');check(len(reused)==3,'three exact named paths reused')
    check(all('Court ' not in e['name'] for e in r['entities'] if e['entityId'].startswith('outdoor_area:ib1000:150000')),'no tennis Court number inferred')
    check(set(delta['surfaceNodeEntityMap'])==set(nodes),'all actual GLB surface nodes matched')
    stats={'surfaceEntities':4,'sourceRoadSegments':line_count,'roadPathGroups':len(groups),'existingNamedPathIdsReused':len(reused),'newRoadEntities':len(groups)-len(reused),'totalNewEntities':len(set(entities)-before),'tunnelSegmentsNotGroundDraped':tunnel_count,'cartographicBoundaryLinesAdded':0,'maximumLocalCoordinateRoundoffMeters':max_roundoff}
    r['counts']['entities']=len(entities);r['counts']['byType']=dict(collections.Counter(e['type'] for e in r['entities']));r['counts']['representations']=sum(len(e['representations']) for e in r['entities']);r['counts']['outdoorExtension']=stats
    r['outdoorEntitiesUrl']='outdoor-entities.json';r['sources']['outdoor-extension-input']={'registrySha256':sha(a.registry),'registryFilename':a.registry.name,'checkedAt':'2026-09-06'}
    delta['counts']=stats
    qa={'status':'pass' if not errors else 'fail','errors':errors,'stats':stats,'sourceRegistry':str(a.registry),'sourceRegistrySha256':sha(a.registry),'oldEntityIdsRemoved':[],'oldEntityTypesChanged':[],'legacyMapChanged':False,'reusedPaths':reused,'sourceRoadsSha256':sha(rp),'sourceSportsManifestSha256':sha(sm),'scope':'Only provided four real terrain/orthophoto surfaces + official StreetCentreline source. 1301 cartographic boundary lines excluded.','networkUsed':False,'projectModified':False}
    write('entity-registry.json',r);write('outdoor-entities.json',delta);write('validation.json',qa)
    print(json.dumps({'status':qa['status'],'stats':stats,'entities':len(entities),'representations':r['counts']['representations'],'bytes':{n:(OUT/n).stat().st_size for n in ('entity-registry.json','outdoor-entities.json')},'reusedPaths':reused},ensure_ascii=False))
    if errors:raise SystemExit(1)

if __name__=='__main__':main()
