# coding: utf-8
import json,pathlib,shutil
ROOT=pathlib.Path(__file__).resolve().parents[1];P=ROOT/'public';DATA=P/'data'
j=json.load(open(DATA/'building-evidence.json'));pois={i['id']:i for i in json.load(open('/tmp/hkust-pois.json'))};out=[]
for b in j['buildings_and_named_facilities']:
 i=b['id'];cat='academic'
 if 'residential' in b['use']:cat='residence'
 if b['use']=='campus-facility':cat='living'
 if i in ['campus-07','campus-08','campus-10','campus-22','campus-48','campus-49','campus-52','campus-53','campus-54','campus-55','campus-56']:cat='culture'
 if i in ['campus-24','campus-25','campus-26','campus-28','campus-29']:cat='academic'
 if i in ['campus-34']+['campus-%02d'%n for n in range(37,48)]:cat='staff'
 status='existing';statusText=''
 if b['status'] in ['under-construction','construction-or-planning','target-completion-2026-opening-unverified']:status='construction';cat='construction';statusText='在建 / 计划或启用尚待核实'
 if i in ['campus-19','campus-34','ug-hall-10','ug-hall-11','ug-hall-12','ug-hall-13']:status='updated';statusText='2026 状态更新'
 if i.startswith('ug-hall-') and int(i.split('-')[-1])>=10:statusText='i-Village · 2026-06-11 开幕'
 desc=b.get('notes','')
 if not isinstance(desc,str):desc=json.dumps(desc,ensure_ascii=False)
 ob={'id':i,'name':b.get('name_zh') or b['name_en'],'en':b['name_en'],'category':cat,'status':status,'statusText':statusText,'description':desc,'source':b['sources'][0],'entityKind':b['entity_kind'],'priority':10 if i in ['campus-01','campus-04','campus-18','campus-19','campus-22','campus-24','campus-28','campus-48','campus-52','ug-hall-1','ug-hall-10'] else 0}
 if i in pois:
  p=pois[i];ob.update(easting=p['easting'],northing=p['northing'],positionEvidence=('官方地图参考点；非测量入口' if p['method'].startswith('official') else '官方示意图配准定位，约50m不确定性'),positionMethod=p['method'])
 if status in ['updated','construction']:ob['geometryNote']='状态按2026官方资料；旧网格可能仍显示施工或旧外观。'
 if b.get('floor_evidence'):ob['floors']=str(b['floor_evidence'])
 out.append(ob)
(P/'maps/library').mkdir(exist_ok=True)
floors=[]
for f in ['1f','gf','lg1','lg3','lg4','lg5']:
 src=pathlib.Path('/tmp/hkust-interior-photo-references/plans/library-'+f+'.png');dst=P/'maps/library'/src.name
 if src.exists():shutil.copy2(src,dst);floors.append({'id':'library-'+f,'building':'campus-04','label':f.upper(),'title':'李兆基图书馆 · '+f.upper(),'image':'/maps/library/'+src.name,'sourceFile':'https://lbcone.hkust.edu.hk/floorplans/','note':'官方楼层平面原图；LG5含放大插图，不作为同尺度完整楼板。'})
for i,f in enumerate(['G/F','1/F','2/F'],1):floors.append({'id':'shaw-'+str(i),'building':'campus-22','label':f,'title':'逸夫演艺中心 · '+f,'image':'/maps/shaw-'+str(i)+'.png','sourceFile':'/maps/shaw-floors.pdf','note':'官方2025-06-09平面图；座席布置随活动配置调整。'})
sources=[{'id':'mesh','name':'香港地政总署 · 三维可视化地图','date':'图幅修订2025-03-27；采集日期未明','description':'8图幅292片真实纹理网格，约328万三角面；预览纹理压至512px，几何不改。','url':'https://portal.csdi.gov.hk/csdi-webpage/metadata/landsd_rcd_1671677054006_62261/html'},{'id':'dtm','name':'土木工程拓展署 · 航空激光雷达地形','date':'2019–2020采集','description':'原0.5m DTM，浏览网格5m。真实高程、保留缺失掩码；配色和海平面为示意。','url':'https://portal.csdi.gov.hk/csdi-webpage/metadata/cedd_rcd_1629267205233_87895/html'},{'id':'map','name':'HKUST MTPC · 校园与电梯图','date':'2026-08','description':'建筑名称、宿舍及新楼状态索引。原始校园图、电梯演讲厅PDF本地保存。','url':'https://publish.ust.hk/univ/maps/Campus_Map_Color.pdf'},{'id':'indoor','name':'HKUST · 官方 Path Advisor','date':'2026-09-05读取；逐层测绘日期未提供','description':'公开建筑轮廓、楼层、可显示的房间多边形与导航节点；按层加载，hidden_from_map内容不展示。','url':'https://navigate.ust.hk/path/app/'},{'id':'library','name':'HKUST Library · 楼层图','date':'网页/图片更新各异；LG1含2026-08-27版','description':'1F、G、LG1、LG3、LG4、LG5六层实际原图，配合官方室内照片。','url':'https://lbcone.hkust.edu.hk/floorplans/'},{'id':'cdo','name':'HKUST Campus Development Office · 新建项目','date':'2026-09-05查证','description':'i-Village已开幕；创新楼Completed；NRB2、医教研究楼及AI计算中心逐项标示状态。','url':'https://cdo.hkust.edu.hk/projects'}]
routes=[{'id':'ltb','title':'1/F 找到 LTB','evidence':'官方路径实查','steps':['在 Path Advisor 选择 Academic Building → 1/F。','LTB 对应最近电梯 Lift 26。官方观察路线 LTB → Lift 26 为48m，约1分钟。'],'note':'距离来自官方导航，不根据三维直线推算。','url':'https://pathadvisor.ust.hk/search/nearest/lift/from/ltb/floor/1/at/normalized/1546,-165,3'},{'id':'lg7','title':'到 LG7 超市与生活区','evidence':'官方目的地与电梯关系','steps':['在主学术楼查找 Lift 10–12。','目的楼层 LG7，Fusion 超市位于此生活区。'],'note':'电梯停靠层和即时开放以现场及官方导航为准。','url':'https://navigate.ust.hk/path/app/'},{'id':'ivillage','title':'经 i-Village 屋顶连接南北','evidence':'CDO 官方项目说明','steps':['i-Village 沿约25m高差山坡布置。','屋顶步道连接北侧学术区和南侧住宅区。'],'note':'仅呈现已证实连接关系，未推测逐步步行线路或无障碍通行。','url':'https://cdo.hkust.edu.hk/projects/jockey-club-i-village'},{'id':'shaw','title':'南门到逸夫演艺中心','evidence':'官方校园图 + 演艺中心平面','steps':['从 South Entrance 对照校园总图定位 Shaw Auditorium。','按当日活动指引选择 Drop-off / South / Garden Entrance。'],'note':'观众厅和后台使用受活动安排影响。','url':'https://shaw-auditorium.hkust.edu.hk/'}]
catalog={'buildings':out,'sources':sources,'floors':floors,'routes':routes,'photos':[]}
(DATA/'catalog.json').write_text(json.dumps(catalog,ensure_ascii=False,separators=(',',':')))
(DATA/'coverage.json').write_text(json.dumps({'checkedAt':'2026-09-05','inventoryItems':len(out),'locatedItems':sum('easting' in o for o in out),'floorPlanImages':len(floors),'meshTiles':292,'meshTriangles':3279083,'terrainVertices':108412,'knownGaps':['Not a complete surveyed BIM','Source 3D revision date is not geometry capture date','Unverified exact wall heights and material dimensions','Not all buildings have public interior coverage','Outdoor routes are topology references, not a verified navigation network']},ensure_ascii=False,indent=2))
shutil.copy2('/tmp/hkust-pois.json',DATA/'poi-evidence.json')
print('Built',len(out),'items,',sum('easting' in o for o in out),'located;',len(floors),'floor images')
