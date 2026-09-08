# HKUST 清水湾校园建筑与室内资料研究

核验日：2026-09-05。研究用途：交互浏览与认路的三维校园模型。资料以官方最新图面、实时官方项目页和宿舍页为主；本报告不是竣工测绘。

## 1. 最新底图与可编辑资源

- 官方资源入口：<https://mtpc.hkust.edu.hk/resources/campus-location-maps>
- 校园 PDF：<https://publish.ust.hk/univ/maps/Campus_Map_Color.pdf>，实际 PDF 元数据标题 `Campus_Map_ColorC&E_Aug2026_OL`。已下载并逐图检查：`/tmp/hkust-campus-aug2026.pdf`；整图 `/tmp/hkust-campus-aug2026.png`；核心区高清 `/tmp/hkust-campus-core.png`。
- 官方 AI 源图包：<https://publish.ust.hk/univ/maps/Campus_Map_Color_OL.zip>（资源入口明确标为 AI；网页工具不解压 ZIP，未在本任务检查内部文件）。
- 演讲厅/电梯 PDF：<https://publish.ust.hk/univ/maps/Lecture_Theaters.pdf>，标题 `LectureTheaters_&_Lift_Location_Aug2026_OL`。本地 `/tmp/hkust-lifts-aug2026.pdf`、`/tmp/hkust-lifts-aug2026.png`。
- IAS 两页访客图：<https://ias.hkust.edu.hk/map/>，PDF 标题版本 202601。可提取文本，便于中英名对照；较 August 2026 总图旧，不应覆盖新状态。
- 最新总图图例：浅灰 Existing Buildings；深灰虚线 Buildings Under Construction or Planning。图上圆圈数字是电梯编号，不是建筑编号。总图没有逐楼数字索引。
- 地图可下载不等于明确开放再许可；学校页面有版权标示。模型中保留来源及原图链接，不宣称官方模型或开放授权。

## 2. 2025–2026 变化与现状判定

| 建筑 | 已核实状态 | 几何/内部信息 | 直接证据 |
|---|---|---|---|
| Jockey Club i-Village / 赛马会创新学生村 / UG Halls X–XIII | 2026-06-11 正式开幕；CDO Completed | 四座、共1551床、约35500平方米；顺25米陡坡布置，四级台地；屋顶步道连接北部学术区与南部居住区。公开户型簇有 Y / V / Linear，分别约27/36/18人 | <https://hkust.edu.hk/news/hkust-hosts-opening-ceremony-jockey-club-i-village>；<https://cdo.hkust.edu.hk/projects/jockey-club-i-village> |
| Hall XI / DJI Hall / 大疆创新楼 | August 2026 总图已用此命名；SHRLO Hall XI 在用 | i-Village 四座之一 | 总图；<https://shrl.hkust.edu.hk/residential-halls/ug/ughall11> |
| Martin Ka Shing Lee Innovation Building / 李家诚创科大楼 | CDO Completed；2026-01-28 实际举行 InnoBay 活动，已使用 | 8层、约5100平方米 NOFA；开放布局；到 LSK 校区的桥及至 CYT 有盖步道 | <https://cdo.hkust.edu.hk/projects/martin-ka-shing-lee-innovation-building>；<https://okt.hkust.edu.hk/news/hkust-innobay-welcome-reception> |
| Daniel & Mayce Yu Research Building / 于崇光伉俪研究大楼 / New Research Building 2 | 在建，实时 CDO 原始 HTML 写目标 Q4 2026；2025-06结构封顶 | 8层，开放实验室/科研/办公，约300研究人员，地面展廊，约60车位；连接LSK；顾问网页给约6060平方米 NOFA及19米场地落差 | <https://cdo.hkust.edu.hk/projects/new-research-building-2>；<https://publications.hkust.edu.hk/Annual_Report/2024-2025/eng/HKUST_AR2024-25-EN.pdf>；工程顾问 <https://www.wobse.com/en/projects/educational/Educational_404/> |
| HKUST Medical Education and Research Complex / 香港科技大学医学教研综合大楼 | 在建，目标 Q3 2028；August 2026 总图深灰虚线 | 8层，约6000平方米为场地面积，不是总楼面面积；临床模拟/技能、实验、教学、医学图书馆等 | <https://cdo.hkust.edu.hk/projects/medical-education> |
| High Performance Computational Facility / HPC5；地图现名 HKUST AI Supercomputing Center | CDO目录 Upcoming；详细页仅写 Target completion in 2026；August 2026图已用新名称；未找到正式开放证据 | 8层；海水泵房及曾肇添室内体育中心旁；数据机房及浸没式冷却 | <https://cdo.hkust.edu.hk/projects/high-performance-computational-facility> |
| Teaching Hub (LG4–LG6 New Classrooms) | August 2026地图列入在建或规划图例；没有进一步证实具体工程阶段 | 何善衡体育馆北侧；楼层标识LG4–LG6，非一幢随意设定层数的独立塔楼 | August 2026总图及电梯图 |
| UA Tower C / Tower D | C于2022、D于2025完成改建，现服务教职员家庭，不能仍全标PG公寓 | 65–110平方米、2–4卧室户型；官方户数是占位符，不应编造 | <https://cdo.hkust.edu.hk/projects/remodeling-works-of-tower-c-and-tower-d> |

重要冲突：搜索索引曾将 NRB2 显示为 Q4 2029，但同次实际打开页面和 curl 下载的实时 HTML 都是 `Under construction (target completion in Q4 2026)`；年报也支持 Q4 2026。不要引用搜索片段的 2029。本地原文 `/tmp/hkust-nrb2.html`。

## 3. 建筑覆盖名录（依据 August 2026 总图逐区核对）

以下不是官方编号。组合建筑、翼、馆内空间必须保留父子关系，不要把每个命名空间都生成为独立楼。

### 北门与主学术建筑群

1. Academic Building / 主学术大楼——主体连续建筑群，向海坡地展开。
2. The Hong Kong Jockey Club Atrium / 香港赛马会大堂——主楼北部入口中庭。
3. Chia-Wei Woo Academic Concourse / 吴家玮学术廊——主楼南北纵向室内廊道。
4. Lee Shau Kee Library / 李兆基图书馆——主楼北部东翼；公开六层图。
5. Ping Yuan and Kinmay W Tang Gallery / 唐炳源唐温金美展览厅——图书馆内。
6. Chevalier Learning Commons / 其士综合研习坊——图书馆内。
7. S H Ho Sports Hall / 何善衡体育馆——北门旁，不能与海滨体育中心混淆。
8. Seal of Love Charitable Foundation Wing / 正爱慈善基金翼——体育馆相关翼。
9. Teaching Hub (LG4–LG6 New Classrooms)——体育馆北侧，状态见上表。
10. Tsang Shiu Tim Art Hall / 曾肇添展艺厅——中庭北侧入口区域；不是海滨 Tsang Shiu Tim Sports Center。
11. Yip Kit Chuen and Yuen Yuk Hing Talent Hub——入口广场北側室内空间。
12. Alumni Commons / 校友中心——入口广场北侧。
13. Mr and Mrs Ho Ting Sik Visitor Information Center / 何廷锡伉俪访客资讯中心——入口广场。
14. Lo Kwee-Seong Building / 罗桂祥楼——主楼西翼中南部。
15. The Hong Kong Jockey Club Biotechnology Research Institute / 香港赛马会生物技术研究所——主楼南段。
16. Hong Kong Chiu Chow Chamber of Commerce Scholar Nexus / 香港潮州商会荟萃廊——主楼南段。
17. The Hong Kong Jockey Club Enterprise Center / 香港赛马会创新科技中心——主楼东侧南端。
18. Cheng Yu Tung Building / 郑裕彤楼 / CYT——主楼南端；8层、GFA约10000平方米、CMA演讲厅354座，2015完成。<https://cdo.hkust.edu.hk/projects/cheng-yu-tung-building>
19. Martin Ka Shing Lee Innovation Building——CYT东南侧。
20. HKUST Medical Education and Research Complex——CYT西侧、Shaw北側的在建用地。
21. Wong Check She Research Center for Environment and Infrastructure / 黄焯书科研中心——Shaw西南、南门旁。
22. Shaw Auditorium / 逸夫演艺中心——南门附近椭圆形独立场馆，三重椭圆环，3层，2021-11完成。<https://cdo.hkust.edu.hk/projects/shaw-auditorium>
23. CLP Substation / 中电变电站——医学楼/黄焯书中心西侧近道路。

### 东南山上李兆基校区

24. Lee Shau Kee Business Building / 李兆基商学大楼 / LSK——山上西侧主楼，8层。
25. Karen Lee Student Mentoring Center——LSK内部/相关空间。
26. Wong Chak Chui Lecture Theater / 王则翠演讲厅——LSK北西端。
27. Daniel & Mayce Yu Research Building / NRB2——LSK东南侧在建科研楼。
28. HKUST Jockey Club Institute for Advanced Study / Lo Ka Chung Building / 香港科技大学赛马会高等研究院 / 盧家驄薈萃樓 / IAS——山上东南端，6层。
29. Kaisa Group Lecture Theater / 佳兆业集团演讲厅——IAS建筑端部。
30. Li Dak Sum Yip Yio Chin Kenneth Li Conference Lodge / 李达三叶耀珍伉俪李本俊会议大楼——IAS南侧。

LSK 8层及IAS 6层有官方已建绿色建筑评估证据：<https://sust.hkust.edu.hk/files/Final_Assessment_-_HKUST_NAB_IAS.pdf>。不要把 Lo Ka Chung Building (IAS) 与较北的 Lo Ka Chung University Center 混为一栋。

### 本科宿舍（清水湾 I–XIII）

官方各楼原址：`https://shrl.hkust.edu.hk/residential-halls/ug/ughallN`，N=1…13。全部链接已在官方目录实际观察；I–IX逐页实时下载核实。概况原始记录 `/tmp/hkust-halls-intro.json`。

| 宿舍 | 别名 / 位置线索 | 官方可支持内部/楼层信息 |
|---|---|---|
| Hall I | Lee Yin Yee Hall / 李贤义楼；中坡、桥连接终点附近 | 与SKCC为同一复合楼两翼、不同入口；双人房。导师服务范围列1/F至8/F，仅可说明这些层存在 |
| Hall II | 主海滨中部、体育场西北 | 11层；住宿占2/F及以上，G/F–1/F其他校园设施 |
| Hall III | Ho Iu Kwong and Kwok Pui Chun Hall / 何耀光郭佩珍伉俪楼；北侧海滨弧形 | 5层；双/三人房 |
| Hall IV | 海滨体育场西侧，Hall VI旁 | 6层；双/三人房 |
| Hall V | UG Hall V (PG Hall II)；北侧宿舍带、SKCC旁 | 5个住宿层、230间双人房；PG Hall II作为历史/地图别名保留，不据别名认定当前PG分配 |
| Hall VI | Jockey Club Tower / S H Ho Tower / 赛马会楼及何善衡楼；I与IV间 | 一个宿舍项目含两命名塔体，10层、16翼；官方总人数574与分项402+192不符，建模不必用冲突人数 |
| Hall VII | Chan Sui Kau and Chan Lam Moon Chun Hall / 陈瑞球林满珍伉俪楼；SKCC东侧、II北侧 | 7层；单/双人房 |
| Hall VIII | 体育场南侧西段长条楼 | 7层；单/双人房 |
| Hall IX | 体育场南侧东段长条楼 | 6层；单/双人房 |
| Hall X | i-Village，GGT南侧/LSK东侧 | 单/双人房；公用洗衣房A在G/F；第7层屋顶连接四楼 |
| Hall XI | DJI Hall / 大疆创新楼；i-Village东北边 | 第7层公用步道；部分V/Y型公共簇；与XII共享G/F洗衣房B，位置在XII |
| Hall XII | i-Village东侧偏中 | 公用步道7/F；官方楼层服务表列到9/F，不应全体简化成7层 |
| Hall XIII | i-Village东南侧最长翼 | 官方楼层服务表列到11/F；G/F洗衣房C；7/F公用步道 |

i-Village各座近似床位页合计是近似值，不与全项目1551强行等同。每座都明确7/F连通的管理处、邮件室、生活休息室、共同工作区、健身室。有内部实景图，但未找到每间房尺寸的完整竣工平面图。不要根据照片伪造精准隔墙。

**范围排除**：Jockey Club Hall / 赛马会大楼位于将军澳、是校外宿舍，不要放进清水湾地形；同名赛马会楼是Hall VI一部分，和GGT、i-Village又各是不同项目。

### 研究生、公寓及教职员居住区

31. Stephen Kam Chuen Cheong Hall / 张鉴泉楼 / SKCC / PG Hall I——和Hall I复合建筑，不是独立任意塔体。<https://shrl.hkust.edu.hk/residential-halls/pg/pghall-skcc>
32. University Apartments Tower A / Tsang Chiu Sang Tower / 曾超生楼——主楼东南中坡。
33. University Apartments Tower B / Lam Po Yu Tower / 林宝茹楼——Tower A北側。
34. Tower C、Tower D——Tower B北端至University Center一带，已转教职员公寓。
35. Jockey Club Global Graduate Tower / 赛马会集贤楼 / GGT——i-Village北側、Staff Towers 12–14西側；8层，2021-09完成。<https://cdo.hkust.edu.hk/projects/jockey-club-global-graduate-tower>
36. Lo Ka Chung University Center / 盧家驄大學中心——C/D北侧；其中Tin Ka Ping Hall / 田家炳厅。
37. Staff Quarters Towers 1–2——主校园最北側。
38. Staff Quarters Tower 3、Tower 4——东北上坡，5–7北側。
39. Staff Quarters Towers 5–7——Hall III西側。
40. Staff Quarters Towers 8–11——A/B东側坡地横向带。
41. Staff Quarters Towers 12–14——GGT东側弧形带。
42. Staff Quarters Towers 15–19——i-Village东側最外缘长弧形带。
43. President’s Lodge / 校长宿舍——最北地块东側。
44. Distinguished Guest Lodge / 贵宾宿舍——校长宿舍与1–2座之间。
45. UniLodge / 水云轩——Towers1–2附近入口点。
46. Staff Quarters Houses1–8 & Apartments1–48——大学道北西侧独立组团。
47. Staff Quarters Blocks P–S——大学道西側近清水湾道的四组住宅。

UA当前官方页面仅A/B用于PG，自给公寓为4单房或3单房+1双床房，附客厅、厨房、浴室。<https://shrl.hkust.edu.hk/residential-halls/pg/pghall-ua>。

GGT公开可支持1/F–7/F各层六走廊A–F，A/C/D/E/F各12单房，B翼6夫妇房，各层共享厨房、公共休息室；是相当有力的功能拓扑资料，但仍不能推出精确墙体尺寸。<https://shrl.hkust.edu.hk/residential-halls/pg/pghall-ggt>。

### 海滨体育、研究设施及户外认路点

48. Tsang Shiu Tim Sports Center / 曾肇添体育中心——海滨跑道北側，带Indoor Swimming Pool。
49. Outdoor Swimming Pool / 室外泳池——室内泳池西北。
50. Ocean Research Facility / 海洋研究实验中心——泳池与HPC附近海岸建筑。
51. HKUST AI Supercomputing Center / HPC5——体育馆/海水泵房旁；当前状态见上。
52. Fok Ying Tung Sports Center / 霍英东体育中心——海滨跑道/球场区。
53. Water Sports Center / 水上活动中心——海岸突出角。
54. Yvonne and Chia-Wei Woo Waterfront / 吴家玮叶斐瑜海滨区——水上中心与球场侧沿海段。
55. Courts1–2；Court4（北西住宅区）；Court7（GGT北側）；Court8（东南Staff Quarters旁）——地图明确所示，不额外猜测缺号球场。
56. Amphitheater / 圆形露天剧场——主楼至宿舍桥附近。
57. Fong Shu Chuen Promenade / 方树泉廊——桥東侧、Hall I附近。
58. Bridge Link / 连接桥——主学术大楼跨坡至Hall I一带。
59. Lower BBQ Site / 低座烧烤场——海滨泳池附近；Upper BBQ Site / 高座烧烤场——东南上坡。
60. Butterfly Garden / 蝴蝶园——主楼东側停车场附近。
61. Piazza / 入口广场及日晷地标——主入口环形中庭。
62. North/South Entrances、North/South Bus Stations、University Road、Ngan Ying Road、Clear Water Bay Road——导航入口必须对应。

## 4. 室内可直接用的资料

### A. 图书馆六层：最有用的当前平面图集

入口 <https://lbcone.hkust.edu.hk/floorplans/>；实际分别读取 `/floorplans/floor/1` 至 `/6` 得到：

| 层 | 直接PNG | 页面引用资源的时间戳 |
|---|---|---|
| 1/F | <https://lbcone.hkust.edu.hk/floorplans/images/1f.png> | 20240521174001 |
| G/F | <https://lbcone.hkust.edu.hk/floorplans/images/gf.png> | 20260304160948 |
| LG1 | <https://lbcone.hkust.edu.hk/floorplans/images/lg1.png> | 20260827164418 |
| LG3 | <https://lbcone.hkust.edu.hk/floorplans/images/lg3.png> | 20250828121645 |
| LG4 | <https://lbcone.hkust.edu.hk/floorplans/images/lg4.png> | 20250828141709 |
| LG5 | <https://lbcone.hkust.edu.hk/floorplans/images/lg5.png> | 20260304151154 |

这些是页面资源缓存时间戳，不是正式竣工日期。勿按旧百科“五层”删掉LG5。

### B. Shaw Auditorium

- 官方 G/F、1/F、2/F 平面图（3页、2025-06-09）：<https://shaw-auditorium.hkust.edu.hk/sites/default/files/2025-06/floor_plans_simple_one_20250609.pdf>
- 座位图（2页、标准Concert Mode）：<https://shaw-auditorium.hkust.edu.hk/sites/default/files/2025-04/SA_Seating%20Plan_Concert%20Mode_797_with%20wheelchair_0.pdf>
- 舞台技术尺寸（3页、2024-10-29版本）：<https://shaw-auditorium.hkust.edu.hk/sites/default/files/2024-11/HKUST-Shaw-Auditorium_Technical-Info_Stage.pdf>
- 演奏主舞台17.4米宽×9.6米深×13米至棚顶；舞台高于观众席1.16米；镜框模式演区13×8.9×8.5米；这些可给室内模型定标。总场馆约850观众与特定797座配置是不同口径。
- <https://shaw-auditorium.hkust.edu.hk/main-hall> 提供Flat Floor / Entire Venue / Concert / Theater / Presentation的官方Matterport入口；可按模式切换核对实景。场馆具有可回缩观众席，不能把一种布局当永恒结构。

### C. 学术主楼 / LSK / IAS / CYT / University Center

- 当前 Path Advisor 首页 <https://pathadvisor.ust.hk/> 实际重定向 <https://navigate.ust.hk/path/app/>。当前公开前端 JS <https://navigate.ust.hk/path/app/static/js/main.c4c44c26.js>（已从实际HTML读取，未继续解析地图数据）。
- 搜索旧 `interface.php?roomno=ltb` 所见的楼层/建筑清单可能陈旧；不要当成已验证当前全部平面。旧界面明确有 Academic Building、CYT、IAS、LSK、Shaw Auditorium、University Center，并主楼LG7/LG5/LG4/LG3/LG1/G/1–7楼层。
- 官方认路服务说明：<https://itso.hkust.edu.hk/services/general-it-services/looking-for-a-person-or-a-place/path-advisor>
- LSK 7/F可下载局部室内布局/活动隔断图（2014旧版，不应默认现状）：<https://dbm.ust.hk/booking/doc/7F_lounge_partition_setup_guide_20141118_p.pdf>
- NRB2官方场地布置图：<https://cdo.hkust.edu.hk/sites/default/files/2025-01/rb2_site.jpg>，来源是实际项目页中的图片src。

## 5. 电梯与演讲厅导航标识

August 2026图确认学术区电梯1–15及17–39（没有绘出16）；CYT35–37、Innovation Building38–39。LSK校区另起1–6，LSK1–4、IAS5–6，必须以“建筑+电梯号”作为键。

LT-A Citi；LT-B Lam Woo；LT-C Padma and Hari Harilela；LT-D Lee Wing Tat；LT-E Cheung On Tak；LT-F Leung Yat Sing；LT-G Chow Tak Sin；LT-H Chen Kuan Cheng Forum；LT-J Chiang Chen；LT-K Mr and Mrs Lee Siu Lun；LT-L CMA。没有LT-I。CB= Tang Shiu Kin Computational Laboratory / 邓肇坚电脑厅，不是演讲厅字母序列。Wong Chak Chui及Kaisa Group是LSK/IAS的另外两个演讲厅。

## 6. 证据边界与交付建议

- 可以做到按最新地图覆盖全部主要楼群、准确命名与坡地相对关系、有证据的楼层、可追溯室内平面层及主要步行连接。
- 仅“Completed”不足证明每个实验室/场地随时向公众开放；HPC尤其没有正式开放证据。模型属性应分“建筑状态”与“进入权限/未知”。
- 对缺少平面图的实验室、宿舍、教职员公寓，先做外壳和有证据的公共空间拓扑；房间示意若提供，应明确标成示意/未核实。
- 官方面积有GFA、NOFA及Site area三种，不可直接混用；不应由总楼面÷层数假装得到实际占地。
- 跨坡同一楼的地面入口和楼层不能通过统一海拔+层高随意推算。i-Village的7/F屋顶步道与高至11/F的局部楼层尤其说明不可整组统一高度。

研究已完成；未修改项目文件。仅临时目录有上述资料，可由模型执行任务挑选复制。
