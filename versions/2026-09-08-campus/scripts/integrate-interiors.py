# coding: utf-8
import json,pathlib,shutil,subprocess
R=pathlib.Path(__file__).resolve().parents[1];P=R/'public';d=json.load(open(P/'data/catalog.json'));manifest=json.load(open(P/'interiors/manifest.json'))
name_map={'campus-01':'Academic Building','campus-02':'Academic Building','campus-03':'Academic Building','campus-04':'Academic Building','campus-05':'Academic Building','campus-06':'Academic Building','campus-07':'Academic Building','campus-18':'Cheng Yu Tung Building','campus-19':'Martin Ka Shing Lee Innovation Building','campus-22':'Shaw Auditorium','campus-24':'Lee Shau Kee Business Building','campus-28':'HKUST Jockey Club Institute for Advanced Study','campus-36':'Lo Ka Chung University Center'}
print('Names in indoor',sorted(set(f['buildingName'] for f in manifest['floors'])))
actual={f['buildingName'] for f in manifest['floors']}
# Resolve official variants conservatively.
for id,n in list(name_map.items()):
 if n not in actual:
  candidates=[a for a in actual if n.split()[0] in a and ('Business' in n)==('Business' in a)]
  if len(candidates)==1:name_map[id]=candidates[0]
for i in range(1,14):
 for n in actual:
  if n.lower()=='ug hall '+['I','II','III','IV','V','VI','VII','VIII','IX','X','XI','XII','XIII'][i-1].lower():name_map['ug-hall-'+str(i)]=n
for b in d['buildings']:
 n=name_map.get(b['id'])
 if n in actual:b['indoorBuilding']=n;b['floors']=' / '.join(f['floorName'] for f in manifest['floors'] if f['buildingName']==n)
 if b['id']=='campus-19':b['name']='李家诚创新大楼'
 if b['id']=='ug-hall-11':b['name']='本科生宿舍11座 · DJI Hall'
 if b['id']=='campus-20':b['name']='医学教育及研究大楼'
 if b['id']=='campus-27':b['name']='余国春伉俪科研楼'
 if b['id']=='campus-51':b['name']='HKUST AI 超级计算中心'
(P/'photos').mkdir(exist_ok=True)
refs=json.load(open('/tmp/hkust-interior-photo-references.json'));photos=[];mapping={'shaw':['campus-22'],'library':['campus-04'],'libstudy':['campus-04'],'ivillage':['ug-hall-10','ug-hall-11','ug-hall-12','ug-hall-13'],'innovation':['campus-19'],'cyt':['campus-18']}
for p in refs['photos']:
 if p.get('use_for_interior_model') is not True or p.get('reviewed') is not True:continue
 src=pathlib.Path(p['local_path'])
 if not src.exists():continue
 key=p['building_group'];ids=mapping.get(key,[])
 if not ids:ids=mapping.get(p['id'].split('-')[0],[])
 if not ids:continue
 dst=P/'photos'/(p['id']+'.jpg')
 if not dst.exists():subprocess.run(['sips','-s','format','jpeg','-Z','1200',str(src),'--out',str(dst)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
 for b in ids:photos.append({'id':p['id']+'-'+b,'assetId':p['id'],'building':b,'title':p.get('space') or p['id'],'image':'/photos/'+dst.name,'source':p['source_page'],'note':'；'.join(p.get('visual_observations',[]))+'。拍摄日期未核实；示范布置不代表每个房间。','floor':p.get('floor'),'sourceImage':p['source_image_url']})
d['photos']=photos;d['interiorStats']=manifest['stats'];(P/'data/catalog.json').write_text(json.dumps(d,ensure_ascii=False,separators=(',',':')))
shutil.copy2('/tmp/hkust-interior-photo-references.json',P/'data/photo-evidence.json')
coverage=json.load(open(P/'data/coverage.json'));coverage.update(interior=manifest['stats'],photoReferenceAssets=len({p['assetId'] for p in photos}));(P/'data/coverage.json').write_text(json.dumps(coverage,ensure_ascii=False,indent=2))
print('integrated',len(photos),'photo mappings,',len({p['assetId'] for p in photos}),'images')
