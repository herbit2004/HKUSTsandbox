# 公开来源、资料日期与查证日

首表为2026-09-05的来源核对记录；后文分别标明后续本地核对与新增来源。精确下载URL、HTTP日期、哈希和处理链以各原始manifest为准。

|来源|原始日期|用途与本地证据|
|---|---|---|
|[HKUST MTPC 校园地图](https://publish.ust.hk/univ/maps/Campus_Map_Color.pdf)|PDF标题Campus_Map_ColorC&E_Aug2026_OL|校园名称、状态、地标；public/maps/campus-aug2026.pdf|
|[电梯/演讲厅图](https://publish.ust.hk/univ/maps/Lecture_Theaters.pdf)|2026-08版|主楼、CYT、LSK、IAS、Shaw等独立电梯编号体系|
|[地政总署三维可视化地图](https://portal.csdi.gov.hk/csdi-webpage/metadata/landsd_rcd_1671677054006_62261/html)|8图幅REVISIONDATE2025-03-27；采集日期未核实|原b3dm/3D Tiles保留；public/models/render-manifest.json、source-geodata/|
|[CEDD航空LiDAR](https://portal.csdi.gov.hk/csdi-webpage/metadata/cedd_rcd_1629267205233_87895/html)|2019–2020采集，原DTM0.5m|8幅TIFF/ZIP保留；public/terrain/terrain-manifest.json|
|[地政总署3D-BIT00](https://portal.csdi.gov.hk/csdi-webpage/metadata/landsd_rcd_1637306559892_42396/html)|下载包2026-04/06修订；单栋ATT含2010/2015/2021等|source-geodata/bit00两个核心图幅，未谎称2026逐栋测量|
|[HKUST新版Path Advisor](https://navigate.ust.hk/path/app/)|应用JS2026-08-22；GeoJSON/CAD本身测绘日期未知|78层、19个来源分组（含泳池，18个building）公开接口；source-pathadvisor/manifest.json及README|
|[图书馆楼层图](https://lbcone.hkust.edu.hk/floorplans/)|逐张更新不同；LG1页面含2026-08-27图、LG5含2026-03-04图|public/maps/library/；不把图片更新时间当楼宇测绘日|
|[Library Where is LG2](https://library.hkust.edu.hk/news-events/news/where-lg2)|新闻2026-03-03，所述为历史设计标高|图纸叠层历史参照；不覆盖Path Advisor逐层源Z|
|[Shaw Auditorium](https://shaw-auditorium.hkust.edu.hk/main-hall)|楼层PDF2025-06-09；座席PDF2025-04；舞台PDF2024-10-29|楼层原图、空间照片和多用途观众厅配置；拍摄日未核实|
|[i-Village开幕](https://hkust.edu.hk/news/hkust-hosts-opening-ceremony-jockey-club-i-village)|2026-06-11|已开幕/1551床；屋顶连接用途由CDO佐证|
|[i-Village项目](https://cdo.hkust.edu.hk/projects/jockey-club-i-village)|2026-09-05页面状态Completed|更新状态与连桥说明；几何另按Path Advisor包络|
|[李家诚创科大楼（旧索引：创新大楼）](https://cdo.hkust.edu.hk/projects/martin-ka-shing-lee-innovation-building)|2026-09-05页面状态Completed|8层与已建成状态；公开楼层Z支撑当前形体近似，不按连接说明推造桥|
|[NRB2](https://cdo.hkust.edu.hk/projects/new-research-building-2)|当前HTML目标Q4 2026|在建，不能按旧搜索索引时间代替当前页面|
|[医教研究大楼](https://cdo.hkust.edu.hk/projects/medical-education)|当前目标Q3 2028|在建/计划；未虚构竣工外观|
|[高性能计算设施](https://cdo.hkust.edu.hk/projects/high-performance-computational-facility)|目标2026；未确认开放|保留启用边界|
|[HKUST SEN无障碍图](https://sen.hkust.edu.hk/access-map/)|更新日未说明|39个设施参考点，非经验证全校园无障碍路网|
|[HKUST官方VR](https://campus-vr.hkust.edu.hk/tour.html)|拍摄日期未公开|6套完整cube场景；Atrium错误资源已按官方XML图块修复|
|[HKUST宿舍](https://shrl.hkust.edu.hk/)|资料日期逐页不同|示范房、公共空间；PG A/B与已改教职员住宅C/D区分|

摄影GLB默认预览将纹理缩至最长512像素，通常保留源几何；本轮仅对两组已实证悬浮的17面生成派生校正，原GLB、原预览及原纹理仍保留。原官方3D Tiles误标12分量sphere的问题修为box，修订前source-tileset.json保留。个别不存在的源LOD文件采用可用祖先避免空洞，并在source-geodata子图幅清单记录。

室内照片的来源页、原图地址、尺寸、SHA256和视觉特征在public/data/photo-evidence.json。原始照片元数据不作为拍摄日期；节点created_at/updated_at仅为后台管理日期。2044个联网节点中仅按需访问选定图像，不把未逐张检查的全部图像称为人工核验。

## 第二轮精度与交互资料

本节保留V2历史快照；其中LOD数量与两栋外观入口不是当前V4配置，现行清单见下方V4段及来源覆盖表。

|资料|来源与日期|交付及证据|
|---|---|---|
|按需原纹理|同一地政总署摄影网格，图幅修订2025-03-27；未新增拍摄日期|`public/models/texture-detail-manifest.json`：292片网格中的原始嵌入图像原字节提取为328份去重文件，最高2048像素；原图哈希和尺寸逐项保留。清晰度切换不生成新图像细节。|
|1m地形分块|[CEDD航空LiDAR](https://portal.csdi.gov.hk/csdi-webpage/metadata/cedd_rcd_1629267205233_87895/html)，本批源图幅采集2019-12-20至2020-02-02，原采样0.5m|`public/terrain/detail/manifest.json`及`sampling-error.json`：55片、5,425,430三角形，保留源缺值。247,614个共同参考点上，相对原DTM的插值RMSE为1m网格0.070m、5m网格0.300m；这是显示重采样误差，不是测绘精度或现状误差。|
|4个真实高LOD局部patch|[地政总署三维可视化地图](https://portal.csdi.gov.hk/csdi-webpage/metadata/landsd_rcd_1671677054006_62261/html)，原CESIUM图幅12-NW-6C中的2/6/11/16子块，修订2025-03-27|`public/models/hires/manifest.json`：high共110片GLB、601,989三角形；2子块另有fine 52片、349,336三角形。`sources/`保留原frontier、source-tileset和下载来源；`validation.json`核对源层级、有效transform、完整覆盖、baseline SHA及GLB原字节复制。不同档位整体替换，不累加。|
|两栋逐栋外观|地政总署3D Visualisation Map (Individualised Models)，12-NW-6C GLTF原包；图幅修订2026-04-24，ZIP Last-Modified为2026-04-02T10:11:41Z|`public/models/standalone/manifest.json`：Shaw `B451872165201063A0`与CYT `B451962174701063A0`，合计8,687三角形。原glTF/bin/JPEG、节点矩阵与直接依赖保持不变；各`source-manifest.json`包含下载URL、名称与官方轮廓比对证据。摄影、测绘、竣工日期均未提供；两个来源时间字段分别保留，不互相替代。|
|命名空间与建筑轮廓|2026-09-05保存的[新版Path Advisor](https://navigate.ust.hk/path/app/)全量base-map及公开楼层几何|`source-pathadvisor/v2-position-evidence/`及`public/data/building-footprints.json`：4个原父楼聚焦项改用具名空间公开几何，另增加1个明确POI，独立定位由34增至39，父楼聚焦由14减至10。原图面配准点没有因此全部获得更高精度。|

图幅修订、ZIP响应日期和本地查证日期均不代表资料采集日；LOD的geometricError也不承诺实测定位误差。1m地形仍使用HKPD；摄影网格、逐栋外观与室内源Z的绝对垂直基准不确定性保持原记录，未添加推测高程修正。

## V4 来源覆盖与实际使用（2026-09-06 本地核对）

以下据已保存的 manifest、源数据和本地验证记录追加，没有重新访问外网。上方“第二轮”描述的是 V2 历史资产与交互；旧三档子块切换及两栋独立查看入口不代表 V4 当前场景。资料采集日、服务修订日与本次本地核对日继续分开记录。

|当前资料|来源、日期与范围|当前资产与证据|
|---|---|---|
|8 个完整外观组|[地政总署三维可视化地图逐栋模型](https://portal.csdi.gov.hk/csdi-webpage/metadata/landsd_rcd_1671676915450_88604/html)；逐栋图幅修订 2026-04-24，原包 Last-Modified 2026-04-02T10:11:41Z，拍摄日期未提供；Academic 补充摄影图幅修订 2025-03-27|`public/models/exteriors/manifest.json`及`academic-supplements/*.source.json`；历史清晰度审计在`docs/source-evidence-v3/source-clarity-and-seams.json`。8 组共 47 个对象，保留原 glTF 矩阵及逐项外部平移/变换。Academic 为 9 个逐栋源对象加 28 个真实摄影补充面；完整组不是新测量或水密 BIM。|
|摄影覆盖与整区原纹理|同一批 292 片摄影网格；源三角形 3,279,083 个。原纹理日期与分辨率保持既有来源限制|`public/terrain/coverage/manifest.json`、`public/models/exteriors/baseline-texture-regions.json`。覆盖遮罩由真实三角形 XZ 投影按 1m 像素中心生成；16,000 个独立参考像素检查为 0 个不一致。19 个纹理区域对应18个building及室外泳池，Coastal Marine Lab已补齐。区域按完整集合提交；地域context不能作为建筑归属证据，不生成额外图像细节。|
|4 个运动场地表|官方 iB1000 图面：跑道外环及场内地面 `1810061356`、足球场 `1810061354`、两片网球面 `1500002494` / `1500002493`；纹理为 2025-01-11、0.25m 正射影像原文件，高程为 2019-12-20 至 2020-02-02 采集的原 0.5m CEDD DTM 插值|`public/surfaces/sports/manifest.json`、`sports-surface-mask.json` 与 `docs/source-evidence-v3/surface-qa.json`。4 面片共 32,860 个三角形；纹理字节未增强或重着色，全部三角形有有效源 DTM。图面、裸地高程和影像不是同期采集；原先北侧网球图面在 2025 影像中已见屋顶，未作为开放球场新增。|
|56 组官方道路、223 段源线|[地政总署 Street Centreline 服务](https://portal.csdi.gov.hk/server/rest/services/common/landsd_rcd_1637310758814_80061/FeatureServer/0)；已保存相交查询范围 WGS84 114.254–114.272、22.328–22.344，输出 EPSG:2326。服务要素更新时间不是道路测绘或通行状态日期|`public/data/outdoor-entities.json` 的 `sources.roads` 保留完整查询 URL、源 SHA256 与 `roadSourceMap`。按 `STREETCODE` 分组，保留完整相交段和相邻道路；无推造路由拓扑、路宽或桥面高程，1 段 Tunnel 不默认作地表线。制图边界线未加入道路实体。|
|海面显示接色|以原摄影覆盖边界、已保存 HWM/SWA 海岸线和 DTM 缺值共同限定范围；已核海岸线北坐标区间 N821600–822200。显示色 `#41666f` 来自 4 个原海面摄影三角形中心 UV 样本的代表值，不是实测水色|`public/surfaces/sea-edge/manifest.json`、`docs/source-evidence-v3/sea-edge-guard.json`、`sea-edge-final-pixel-qa.json`。仅在遮罩内、摄影片元 Y=0–3m、距离已知岸线满足保护条件的位置，把输出线性色平滑接到背景水色；原纹理文件和几何未删除、移动或改写。|

运动场正射影像原文件 SHA256 为 `b00cbcc456ea6029a0cd648476d7e8cbb80325d995fefe45728c61a898670239`；manifest 还保留原下载恢复验证路径及 UV、有效 DTM、三角形边界检查。地表来自真实图面与裸地高程，跑道外环派生的场内覆盖不等同于新增测量的跑道分道、看台、围栏或足球设施模型。

海面处理应表述为“海面显示颜色接合改善”，不称新增真实海面、影像、水深、海岸线或水色测量。当地形有有效高程或靠近已知岸线时不应用该效果；本地保护检查中 533 个海岸线顶点、502 个运动场边界顶点均未取得非零接色权重。最终同视角截图记录的两条旧硬边 RGB 反差从约 170.40 / 169.82 降至 0.023 / 0；这是特定验收视角的显示比较。截图实际编码为 JPEG，不能声称全图字节或逐像素一致，也不推广为所有相机、所有校园海岸已完成。

历史V3的来源 ID、关系和引用检查记录于 `docs/entity-validation-v3.json`：4,348 个实体、4,680 个表示、78 个来源楼层所关联的 4,301 个可交互房间部分、704 个已出现连接点停靠。公开底图多边形仍保留几何，但不据其隐藏名称生成可交互房间。多标高、可空源字段和 CAD 缺失状态由 `app/source-types.ts` 原样表达；`docs/camera-validation-v3.json` 另验证地下层许可、孔洞、多 Z、NoData 和细地形采样。上述程序验证只证明本地组织与实现的一致性，不提升来源本身的测绘精度或现状时效。


### V4 当前形体与影像资料

[CDO创科大楼项目页](https://cdo.hkust.edu.hk/projects/martin-ka-shing-lee-innovation-building)为已保存的Completed状态与8层说明来源；[官方校友中文介绍](https://alum.hkust.edu.hk/zh-hant/highlight-story-febmar-2026)使用李家誠創科大樓，[InnoBay欢迎活动](https://okt.hkust.edu.hk/zh-hant/news/hkust-innobay-welcome-reception)提供2026-01-28楼内使用证据。实体使用简体正式名“李家诚创科大楼”，旧“创新大楼”为别名，现状证据不把旧摄影自动变成新测量。

近似外观参考CDO的[宽面照片](https://cdo.hkust.edu.hk/sites/default/files/2026-06/20260320_111131.jpg)（4000×3000）与[转角照片](https://cdo.hkust.edu.hk/sites/default/files/2026-06/20260421_160149.jpg)（2000×1500），已逐张看图确认；原网址和SHA见`public/models/current-forms/innovation/manifest.json`。文件名和2026-06上传目录只提供日期线索，`captureDate`仍为null。室内走廊图`20260526_161959.jpg`未用作外墙参考。

几何来自已保存PathAdvisor建筑图面与8层286个公开多边形部分，源Z为131.95、136.95、141.95、146.95、151.95、156.95、161.95、166.95。GLB保留这些源楼层，立面色带为照片参考近似；最高层上方5m和171.95封顶只是显示参数，`roofHeightMeasured=false`。桥项目尚缺完工确认，本模型未推造桥。原楼层与近似立面节点在manifest/GLB中区分，不称竣工BIM或新摄影模型。

创科大楼两张官方照片加入后为43张照片；其后的红鸟地标补充6张，当前`public/data/entity-resources.json`为49张照片与2,050个全景。V4初始实体报告`docs/entity-validation-v4.json`记录4,348实体、4,681表示、8个原始外观组/47源对象及1个独立current-form模型；红鸟新增后的当前统计另行更新，不把近似模型当成第9组原始外观。创科大楼几何检查及四类拒绝负例见`docs/source-evidence-v4/innovation-*.json`。

### 覆盖审计与运行状态

逐栋来源表见[SOURCE-COVERAGE-v4.md](SOURCE-COVERAGE-v4.md)。`source-evidence-v4/source-audit-before.md`及`building-source-coverage.json`保留修复前快照，其中“18区域、Coastal Marine缺映射”是当时结论；当前manifest已为19区域。原纹理共328张，最高2048像素；已核实建筑区域中的最大原图为1024像素，8个独立外观组另有最高2048–8192像素原图。图集像素尺寸不代表立面每米像素或拍摄时效。

当前高清档完整外观640MiB只计基础RGBA加mask，原图缓存192MiB计精确完整mip链；初始128MiB固定原图预算保留在早期V4报告中。两者都不是浏览器或GPU总占用。来源可用不等于当前可见，缓存/延后/失败也不等于没有来源。受控加载测试与具体浏览器状态保存在`docs/source-evidence-v4/`，历史V2/V3验收不改写成V4验收结果。海面接色仍只是显示处理，不是水色、海面高程或水深测量。


### 入口地面与红鸟日晷的多来源表示

入口面片来源见`public/surfaces/entrance/manifest.json`：原TDOP图幅T12-NW-A，摄于2025-01-11、0.25m/像素，裁片660×1080；几何为2019–2020原0.5m CEDD DTM（HKPD），边界取已保存iB1000公开线网围成的图面，逐块对照官方广场照片与正射影像。图像像素没有增强或改色。mask逐像素保存参考地面高程，仅在地面上1.75m范围内替换竞争摄影表面；排除圆台、雕塑、建筑、树冠及花坛孔洞。此表示不是2026铺装或台阶测量，来源坐标分辨率也不是位置精度证书。

[CMO日晷页](https://cmo.hkust.edu.hk/sundial-sculpture)确认Red Bird、Sundial与Circle of Time为同一雕塑，由Charles与Joan Walsh-Smith创作、1991-10-08安装，位于Entrance Piazza中央；引用设计提案的主体高度为8.5m。已保存品牌指引印刷页73使用正式名“红鸟日晷／The Red Bird Sundial”，PDF修改日期2025-12-03。CMO浮雕提案7.0×1.5m和图注9m不一致，未据此假定浮雕尺寸。

主体使用[OpenRedBird3D社区重建](https://github.com/HKFoggyU/OpenRedBird3D)，commit `8d42b92cca54d9da26f75b0f7ea4fd6adea3168e`（2022-10-13），MIT，Copyright (c) 2022 Hong Kong Foggy University。原STL、生成器与LICENSE保存在`public/models/landmarks/sundial/community-source/`。原模型为100mm打印用途，未带现实坐标；已去除打印底座并按官方8.5m定标，统一红色，补官图可见的近似细斜杆。主体源面按转换保持，不是官方CAD或有现实精度认证的测量模型。

六张绑定官图包括4张[CMO页面细部](https://cmo.hkust.edu.hk/sundial-sculpture)和[Marketing广场实景](https://mscmark.hkust.edu.hk/sites/default/files/styles/location_image/public/2023-04/20220428UST1057_1.jpg?itok=GY6L2Nxk)、[SENG广场俯视](https://seng.hkust.edu.hk/sites/default/files/styles/lpm02/public/2019-09/W2905_077_925x450.jpg?itok=KYKRwx7M)。CMO side-a/c/d的嵌入EXIF分别是2004-10-26、2004-10-04、2004-10-05；其他图拍摄日未核实，不把文件名或上传目录当拍摄日。细部depicts红鸟，广角depicts广场并与红鸟nearby绑定，旧照片不能证明2026池水或地面状况。

红鸟位置来自正射图核对的iB1000近圆图面`1101824872`中心localXZ `[336.40017,-1549.93417]`；它不是池径或锚点实测。基准Y约123.145为摄影网格附近表面环中位数的显示配准，DTM裸地121.729没有用作台座顶。真实原摄影台阶和水池保留。manifest保存每份源hash、图像日期、许可与转换边界；GLB真实解析、逐源顶点复算和关系/照片拒绝负例均有独立报告。

当前7个摄影patch仍源于同一地政总署摄影包，13个frontier去重引用585份GLB。完整来源6C-2/6/11/16的fine分别为53/83/66/57个error=0末叶；局部6C-1/7为91/68叶，仍缺兄弟源，不能声称完整父瓦片覆盖。UG10局部37叶在high字段下已经terminal，最高档复用它。其他high可以包含中间LOD，整组互斥并只按实际投影替换。无新增摄影日期。当前画质预算以`app/quality.ts`及[来源覆盖表](SOURCE-COVERAGE-v4.md)为准，auto仅观察CPU提交耗时，不视为GPU显存或真实FPS实测。共享4317使用完整快照原子切换，最终浏览器验收见`QA-v4.md`。

当前电梯专属核对为74对象/331条停靠；459个connector/704条stops还包括楼梯及扶梯。官方总图、学生指南与源房间位置只在各自证据范围内交叉核对，未据单一图例新增停靠；详见`source-evidence-v4/lift-cross-check.md`。


### 已核候选，尚未导入

来源研究已确认[Hugging Face BobH62/SLABIM](https://huggingface.co/datasets/BobH62/SLABIM/tree/main)提供`BIM.zip`，96,380,034字节；项目作者COLLABORATOR BobH62在[issue #2的原始留言](https://github.com/HKUST-Aerial-Robotics/SLABIM/issues/2#issuecomment-2689929971)发布入口。HTTP Range中央目录显示1F–5F共25项，每层包含DXF及columns、doors、floors、walls四类PLY。已检查5F DXF的`INSUNITS=4`（毫米），XY仍是未配准本地坐标；PLY没有单位标签，不能直接沿用DXF单位。

这份as-designed候选不等于当前竣工状态，也不是论文所述LG7–7F的全楼数据。仓库GPL不能自动授权外部BIM.zip；包内及数据卡未见许可，来源研究未给出可继承的外部资产许可。本轮没有导入、配准或据其替换现有室内几何；候选来源存在不增加实际覆盖数。

USTransit的iOS应用内部菜单尚未核查，电梯入口保持“未验证”；商店公交截图不能证明该应用没有电梯功能。多个客户端若展示同一Path Advisor上游，也不能当成多份独立设备/停靠来源。

## 最终局部细节与源残片校正

`public/models/hires/partial-entrance/`和`partial-entrance-6c7/`保留6C-1/6C-7原源GLB、CRC/SHA、层级和真实投影mask。fine分别为604,746与370,583面，所有记录的originalError为0；high仍有0.8660253882408142的中间节点，不能把high标成最高原模型。缺失兄弟仍保留原有摄影表面，不新增拍摄日期。当前摄影细网格预算为high 1024MiB、ultra 1792MiB，含有限mip链和局部mask；完整独立外观预算仍是640/800MiB的基础RGBA+mask，口径分开。

Academic RG投影的R保留完整9本体+28补片来源，G仅是9本体实际source triangle union。`core-mask-validation.json`与`build-core-mask.py`可核对源哈希、矩阵、0.5m栅格与不变的R；运行时细摄影绕过旧supplement coverage，但继续避让G本体。没有复制同一批高清原图进另一套Academic补片。

UG10源11A-3的9面及UG12/13间11A-4的8面经源B3DM/GLB字节比对、孤立组件距离、垂直射线和相机投影确认为摄影悬片。`public/models/source-corrections/`保留原source引用、固定0基面索引、派生文件与逐保留面POSITION/UV一致性测试；原始3,279,083面仍保存，当前派生预览3,279,066面。UG10的before/after实景界面截图由主线验收保存；第二组在同一UG10相机右屏外，不能把该截图称为它的视觉验收。源L16连续屋顶与立面本身仍粗糙，原图1024px图集不是近景足够清晰的保证；更高源分支是否可用应另有清单和加载证据。

UG10局部末叶资产为`public/models/hires/partial-ug10/manifest.json`：37份source error=0叶、原传输11,190,304字节；原B3DM/CRC与GLB存档。最终283,713显示面，基础RGBA136.0625MiB、精确mip181.416629791MiB、mask0.262664795MiB；source role仍为四树地理片段，不是新增独立building外观。fine中的旧悬片使用两个新连通组件593/336面分别校正，保留其余源POSITION/UV及图像字节；没有把旧9面索引套到细叶。19,586个独立像素中心零不一致，两处已知悬片体积均无新三角回填，未新增摄影日期或测绘精度承诺。


### 当前界面与验证记录的来源边界

界面身份为校徽与固定HKUST；三语沉浸显示使用DOM布局，不调用原生fullscreen API。侧栏、画布与标签以真实可用DOM矩形统一投影，恢复保留原用户设置；资料入口保持实体→资料→返回，别名及长原始归属链在详情保存，照片的depicts/nearby和已核captureDate按源分别显示。这些是表达与交互改进，不增加测绘来源或实体所有权证据。

当前建筑面拾取依据18栋官方面域及8个明确归属模型组，两类重合，不能据此声称32栋均可面选；其余14栋边界仍在本地证据审查。`source-evidence-v4/entity-picking/qa.json`保存源三角与裁切归属检查，不把AABB、原图区域或50m图面参考点当实体边界。

现行预算high/ultra摄影细网格为1024/1792MiB，完整外观仍640/800MiB基础RGBA+mask，原图缓存192/384MiB含完整mip链。`quality.ts`在初始载入结束、资源计数稳定1.5秒后才采样场景CPU耗时；持续慢可降档，5个稳定快窗口且45秒冷却后可恢复至硬件初选上限，不是GPU计时或显存测量。

当前受控报告分别为PAN 25/25、detail 44/44、quality 5/5、UI 9/9，见`motion-component-checks.json`、`detail-loading-tests.json`、`quality-checks.json`、`ui-session-tests.json`。`entrance-terminal-ultra.json`保存入口四组fine的1,874,776面、1,831,115,908字节该流驻留估算及mesh/exterior 0失败。此前崩溃没有完全归因；后续fresh Auto/High/Ultra的0失败只描述已验收会话，不宣称所有设备/视角绝不会崩溃，最终范围由`QA-v4.md`记录。
