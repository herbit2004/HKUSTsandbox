## 2026-09-08 U72：创科材质统一及固定4317发布

> 公开仓库说明：本文引用的用户原话、历史截图和部分证据附件仅保留于完整本地工程，不随公开 clone 分发；目标要求及未完成状态继续有效。

固定 `http://127.0.0.1:4317/` 已原子切换到快照 `20260907T192536948257Z`。HTTP返回的首页、创科manifest、14,899,176-byte GLB和三贴图验证报告均与工作区逐字节相同；GLB SHA-256为 `eeaf75c640247a05bc78c437bf29fc397018938c98d0a01f1eab5e0e8b152c56`。候选真实页面加载292/292、Ultra，current-form/mesh/exterior failure均为0；固定页发布后CUA因macOS再次锁屏尚未完成视觉截图，证据边界保留为“已发布且字节通过，固定页视觉待补”。

创科楼本轮保持原bounds，外墙两张官方照片使用统一低饱和灰蓝显示校准，未贴图结构用显式`campusBakedLighting`显示单次固定方向受光；8个明确roof/terrace渲染面加入已有来源记录的current-form铺装材质族。最终79个Three mesh中65个属于默认外观，64个外墙和8个屋顶/露台mesh有贴图，三张图均嵌入且与登记文件逐字节相等，外部请求0。屋顶材质只作为current-form材质家族近似，不能称创科屋顶实测饰面；八层外包络、对向立面和屋顶高度仍受限。

类型检查、照片材质9项、结构阴影17项、current-form contract、完整组14项、驻留13项、registry、点选37项、资源池及六段保存相机轨迹回放检查通过。Ultra曾超楼轨迹允许一次视野边缘frontier收敛，之后没有高/低层往返；其他五段外观/mesh/原图集合均为0次变化。Hall I–III审计候选因误用Hall X–XIII包络被拒绝，没有应用其任何删除。U71两组悬浮旧源修正继续保留，G39全邻域仍未完成。

证据：[发布字节核对](source-evidence-v4/published-stage-u72-innovation.json)、[创科U72审计](source-evidence-v4/building-quality/innovation-material-runtime-audit-u72.md)、[生命周期核对](source-evidence-v4/building-quality/current-form-lod-unity-u72.md)、[被拒绝的错误域审计](source-evidence-v4/ivillage-remnants/hall123-remnant-ground-audit-u72.md)。

## 2026-09-08 U71：Hall XI/XIII悬浮旧源已发布到固定4317

固定 `http://127.0.0.1:4317/` 已原子切换到快照 `20260907T180419486262Z`。固定页重载后292/292、Ultra、目标Hall XI fine owner及mesh/exterior failure=0均复验通过；三份manifest与三份修正GLB的HTTP返回字节和工作区完全一致，见[U71发布记录](source-evidence-v4/published-stage-u71-floating-remnants.json)。

本轮新增两项SHA绑定的源级修正：Hall XIII在L21 terminal tile删除一个完整1,310面连通组件；Hall XI在同一owner的high/fine层分别删除258面和10面。Hall XI的fine修正完整嵌套已有`hall11-floating-rock-v2 → ug10-refined-source-isolated-fragment`来源链，没有从更早未修正GLB重做。顶层高清manifest、native-corridor manifest、对应descriptor和residential/IAS aggregate已同步；native high/fine与aggregate三个受影响遮罩均从实际保留三角重新栅格化，并经像素级重建比较通过。

候选 `http://127.0.0.1:4331/` 实测292/292基础瓦片载入；Hall XI标准视角使用目标owner fine，放大视角使用同owner high，海岸反向视角也完成检查，三处mesh/exterior failure均为0。此前悬挂的高柱状石块和配套白色残片不再出现，未见新增楼面、道路、树冠或current-form孔洞。截图中仍可见的施工期地面和楼脚接缝属于G36/U62，不能由本次精确残片删除销项。

全邻域基线只读审计覆盖4个preview瓦片、4,895个连通组件，其中734项满足“小、孤立、明显离DTM、未命中current-form/官方楼域”的数值条件，但安全自动删除数仍为0；每项都必须先取得多角度运行owner证据，避免把屋顶构件、树冠、挡土墙和坡面当残骸。G39继续未完成。复现与证据见[Hall XI U71](source-evidence-v4/ivillage-remnants/hires-remnant-audit-u71.md)、[Hall XIII U71](../public/models/hires/source-corrections/ivillage-hall13-boundary-remnant-v4/evidence.json)及[基线候选审计](source-evidence-v4/ivillage-remnants/hall-x-xiii-preview-component-candidates-u71.md)。

本轮还完成了[现状形状核对](source-evidence-v4/ivillage-current-shape-u71.md)和[点选差距表](source-evidence-v4/building-quality/selectability-gap-u71.md)。用户俯拍图可支持四栋、台地、庭院和屋顶步道的定性关系，不能在无标定时直接改楼形；Hall XI共享边界仍需as-built证据。57个building/shared scope中53个已有静态真实网格射线，4项是两栋施工/规划记录与Hall VIII/IX两个共享域成员；全校全LOD浏览器直接点选尚未完成。

## U69 Hall X–XIII楼形真值与生成俯拍图拒绝（2026-09-07）

- 用户观察正确：刚生成的俯拍候选没有守住“只改局部施工期地面”的约束，不能用来判断或修改楼形。
- 用同一套HKUST PathAdvisor官方楼宇边界叠到2025注册TDOP与生成候选：源图为EPSG:2326、0.25m/px、1080×880；候选原生1389×1132，先Lanczos回到同尺寸后才比较。
- 全图平均RGB绝对差40.87，81.15%像素变化超过15；四栋官方楼域内平均差63.95、88.54%像素变化超过15、边缘相关系数-0.014；官方楼域外15m控制区仍有80.46%像素变化超过15。它重画了整个画面，不能视为配准纹理。
- 决策：`publish=false`、`copyToRuntimeAssets=false`、`reshapeBuildingsFromCandidate=false`。平面形状沿用保存的官方PathAdvisor楼域；旧源屋面/地形接缝可由终级摄影三角约束；2026校方照片只核对现状体量、真实连接和材质，不在无相机标定时反推精确俯视边界。
- 复现：`python3 scripts/review-generated-ivillage-ortho.py <candidate> --report docs/source-evidence-v4/ivillage-rebuild/generated-overhead-rejection-u69.json --comparison docs/source-evidence-v4/ivillage-rebuild/generated-overhead-review-u69.jpg`。
- U69新增悬浮石块反馈已写入G39；需在Hall X–XIII全邻域对所有悬空旧源连通块完成多角度定位、修正与复验，当前保持未完成。

## 2026-09-07 U69：canonical身份修正已发布到固定4317

固定 `http://127.0.0.1:4317/` 已原子切换到快照 `20260907T133858636920Z`。实际HTTP返回的首页、`catalog.json`、`entity-registry.json`、高清清单、iVillage现状模型清单和Hall XIII遮罩均与快照及工作区逐字节相同；catalog/registry SHA-256分别为 `ba808be4ccb69d5599808898eda67ca7b8253feaa2f28984c87e16b55be117ed` 和 `5bcbea0b691aa08c85f06a4129b4d866d975b28282349b6df1779225fc07f1f3`。

除罗桂祥楼外，官方一手资料进一步确认：李兆基图书馆、何善衡体育馆属于主学术大楼的命名区域；张鉴泉楼是本科生宿舍I同一复合建筑的另一翼。四者保持 `space` 身份和真实父级，不复制父楼外壳。医学教育及研究大楼、Daniel & Mayce Yu科研楼继续保持在建/reference-point-only；稳定校验禁止因相邻摄影三角面很近就误认领owner。当前canonical gap审计已无未判定的现存building-like名称；贵宾宿舍与水云轩仍是有现行服务名、但无独立楼域或宿主等价证据的两项边界。

真实固定页面中，搜索“罗桂祥楼”显示“空间 · 主学术大楼”；Hall VIII/IX共同区域卡片清除搜索后列出8座与9座，两成员卡片均可打开。该浏览器检查只证明身份层级和成员路径，不替代全校逐栋、全LOD屋顶/立面的真实WebGL直接点选。证据见[发布记录](source-evidence-v4/published-stage-u69-canonical-inventory.json)、[命名空间归属](source-evidence-v4/building-quality/named-space-containment-u69.json)、[在建owner边界](source-evidence-v4/building-quality/construction-owner-boundaries.json)和[浏览器QA](source-evidence-v4/building-quality/fixed-page-browser-qa.json)。

## 2026-09-07 U68：楼体邻域终级源接入并发布

固定 `http://127.0.0.1:4317/` 已原子切换到快照 `20260907T012605628161Z`。实际HTTP返回的 `models/hires/manifest.json` 与工作区SHA-256均为 `dc85697a9e29cf7cfa2f8b1627026cab1adf4640dc136fadd5860c5a17334c72`；生产清单现有167个owner、601个high瓦片、1701个fine瓦片。

U67的“靠近并停留仍不会变清楚”存在两层原因。96个逻辑遮罩槽已解决“清单已有高层、运行时却无法提交”的状态机饥饿；U68继续解决“空间根本没有生产高层”的覆盖缺口。按53个已有可靠实体范围的canonical building/shared-zone及10m邻域，新增84个完整L18 owner。构建阶段逐项读取并校验643份去重源payload，覆盖84个high与84个fine表示；独立验证重新检查ZIP CRC、b3dm/GLB长度、变换、边界、三角形、纹理mip及0.5m逐像素遮罩，168层、0个不一致。生产集由83个owner增至167个，292个基础摄影瓦片中具有运行时高层owner的数量由18增至39。

真实Chrome/WebGL Ultra路线依次检查Hall II、Hall IV、Staff Apartments 1–12，再返回Hall II：

| 视角 | 可见owner | 其中U68新增 | fine | 遮罩槽 | 动态池计费 | 峰值超限 | mesh/外观错误 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Hall II | 28 | 20 | 27 | 28 | 2042.672MiB | 0 | 0/0 |
| Hall IV | 41 | 35 | 29 | 41 | 1683.186MiB | 0 | 0/0 |
| Staff Apartments 1–12 | 10 | 10 | 10 | 10 | 1178.774MiB | 0 | 0/0 |
| Hall II返回 | 28 | 20 | 19 | 28 | 2042.672MiB | 0 | 0/0 |

这证明本轮覆盖范围具有可达的终级表示，并能在切区返回后按完整预算恢复；返回Hall II有9个owner保持high，是当前视野内整组预算选择结果，不是永久无升级路径。截图与完整运行状态见 [U68运行记录](source-evidence-v4/building-quality/building-neighborhood-runtime-u68.json)，源接入与独立校验见 [U68接入记录](source-evidence-v4/building-quality/targeted-terminal-integration-u68-all/integration.json)。

**范围仍未完成。** 另外253个基础瓦片位于本轮可靠楼体邻域之外，主要涉及更远道路、海岸、山坡和树冠；部分截图边缘仍能看到粗糙树块或源时代融化面。终级源本身粗糙、Hall X–XIII施工期地面或缺失结构必须用现状证据重建，继续靠近或重复接入同一源不会改善。G37与全校视觉验收保持未勾选。

## 最新反馈 U56–U57：颜色与旧源残片仍未通过

固定4317已在快照 `20260906T102640764967Z` 载入 Halls `a865739f…` 与创科 `31cbdeee…`，实际IAB源码为 `index-CTFay4B4.js`。U56明确退回过纯蓝色和受光不足，U57截图及IAB现场又确认三处贯穿多层的旧摄影残带。下方历史结构测试和旧快照说明均不能覆盖这两个失败。

U56修正候选 `14ce1982…` 保留原图/UV，统一蓝灰显示校准、固定世界法向受光和四楼共同几何遮挡，299880个有效三角面；离线图与实际资产检查通过，尚待最新页面复核。U57已定位为裁切源面归属及局部高程下界漏面，正在修正，不能据色彩候选通过判残片消失。真实失败画面及DOM版本记录见 `source-evidence-v4/ivillage-remnants/`。全校G26/G33继续未完成。

## 最新用户视觉复验：G26/G33 未通过（U52–U54）

已发布四栋统一GLB的结构与加载检查通过，不等于产品视觉合格。用户明确指出 X–XIII 与环境割裂、周围粗糙仍像工地、楼外悬挂旧残片；重建材质过于干净，缺少其他摄影楼的光影。李家诚创科大楼同样存在。后续必须将建筑与紧邻环境整体校准，统一几何清理、照片材质与光照观感；两个区域作为明确待修样本，不能靠结构schema或固定淡光照宣告一致。

## 2026-09-06 Hall X–XIII 整组重建及 U51 连廊反馈

- 固定预览已原子更新至 `20260906T085729850327Z`，入口仍是 `http://127.0.0.1:4317/`。前一轮080624的纹理/原生分块/标签滚轮实现保留。
- 四栋改为单一自包含GLB、四个稳定实体根、共享11材质及1张生成陶瓷albedo；独立窗洞/窗框/遮阳、源屋面拟合、核心筒和坡形光伏顶棚。各楼原有楼层/房间记录没有修改。替换须等待完整GLB和四份SHA校验遮罩就绪后整组提交；开楼层仍独立隐藏对应根。
- 原来的X/XI、XI/XII、XII/XIII三维高度差遗漏封口已补；独立审查的21个原穿透射线样本已报告复验无漏，见持久化接缝报告。替换边缘1032个地面像元有真实源三角形命中，BA旧X楼身保护已清除；无新生成地面盖板。
- 结构/真实资产整组加载13项/完整144180像元联合遮罩检查通过。**未据此宣布四栋或全校视觉合格**；浏览器多角度外观、开层后邻楼/地面和直接点选正检查。屋面/构件尺寸仍为有来源约束的近似。
- U51用户指出Hall II上山连廊中段模糊方盒和断口。完整6个owner、67个GLB和12个high/fine前沿已暂存并校验，生产83清单未变。最高源仍有119个细分面落在封闭侧墙平面内、约1.9m接头空隙也仍在；补缺失分区不能修复真实开放连廊结构。官方CMO、Registry及PathAdvisor照片证实开放侧面、斜撑和透明屋盖；两个导航节点的同一张全景已去重，不作双机位测量。见[source-audit.json](source-evidence-v4/hall-2-corridor/source-audit.json)，G09保持待修。

## 2026-09-06 U52–U54 实拍材质候选（历史阶段；后于102640发布）

Hall X–XIII与李家诚创科大楼的“过白、过平、与摄影环境割裂”按同一标准继续处理。Halls候选以官方原照片窗框/窗带对应替代单张重复生成蓝瓷砖，保留砖色渐变、玻璃反射及原照片光影；核心筒及屋顶铺装使用实际可见像素。遮挡最低行排除，不把树枝贴入窗墙。UV在窗框、窗带处分割，照片未见立面明确为材质家族复用，不能称为实测全楼摄影投影。

共享生成/审查代码为`photo_materials.py`与`render-photo-candidate.py`；候选位于`/tmp/hkust-ivillage-photo`及`/tmp/hkust-innovation-photo`。glTF纯色参数统一按线性编码，照片保持sRGB，离线审查也按此转换。新材质改善不等于几何和周围环境已修好：创科灰顶/退台、Halls屋顶细节与周围施工残片、连续道路/树荫仍需实景和运行验收，G26/G33不关闭。

# V4 集成验收与全校逐栋质量

状态：执行中，用户已解锁，恢复真实页面验收；目标未完成。用户当前完整标准见 [GOAL.md](../GOAL.md)。全校视觉质量尚未通过，不能把少数清晰楼体或已下载文件数量汇总成全校完成。

固定本地预览：<http://127.0.0.1:4317/>。`scripts/preview-update.py` 在类型检查和构建成功后原子切换完整快照，旧快照在构建期间继续服务。

## 2026-09-07 U69：canonical点选分母与罗桂祥楼归属修正

旧“53 direct + 6 list-only”统计混合了不同物理角色。当前校验将六行拆为：2个施工/规划记录（医学教育及研究大楼、Daniel & Mayce Yu科研楼）、2个无独立楼域的现行住宿服务名（贵宾宿舍、水云轩）、2个已有共同可点击外壳的Hall VIII/IX成员身份。共同Hall外壳点击后仍列出VIII、IX两个成员；没有按最近点或猜测分界复制网格。罗桂祥楼由科大官方说明核实为主学术大楼的实验室楼段；李兆基图书馆、何善衡体育馆和张鉴泉楼也已由官方一手资料分别归入主学术大楼或本科生宿舍I复合建筑。项目保留四者的 `space` 身份和真实父级，不再把它们误列为缺失独立楼，也不复制父楼外壳。校验与证据见[点选分类审计](source-evidence-v4/building-quality/list-only-building-pick-audit-u68.md)、[当前canonical gap](source-evidence-v4/building-quality/canonical-building-inventory-gap-u68.md)、[命名空间归属](source-evidence-v4/building-quality/named-space-containment-u69.json)和[罗桂祥归属](source-evidence-v4/building-quality/lo-kwee-seong-containment-u69.json)。这项修正没有关闭G11–G12；贵宾宿舍、水云轩的物理范围及全校园真实浏览器逐栋点选仍未闭环。

## 2026-09-07 U69：Hall XI已定位悬浮残片清理并发布

固定4317当前快照 `20260907T133858636920Z` 保留三组source correction：分别删除1,572、769和2,464个有截图射线与source topology约束的旧源三角面；另以899个0.5m currentForms marker把对应区域在所有LOD层交还给既有DTM，避免只在终级L20隐藏、缩放或切层后又冒出。固定4317实际HTTP返回的 hires manifest SHA-256为 `308ad4e90497abbac566b5e00bfa3a6ff1583d4ce515b7c6138e4cb67a3fb501`，current-form manifest为 `29fc0cdac3dc2c8f55ce4a1f04ce6aaf8d083167682743bf4b64a632ffe888fe`，Hall XIII mask为 `22c39aa0fbe28ab14d2fc2db4abfe32fa57255b7d1ff22412595b4501d7a2d26`；均与新快照和工作区逐字节相同。

固定4317的wide、close、second-angle稳定帧及0/500/1500/3000/6000ms过渡帧已经重采集。current-form驻留，三个稳定姿态均收敛，mesh/exterior failure为0；500ms起加载队列为空，随后未观察到目标残片重新出现。TypeScript、生产构建、52项detail loading、current-form set/coverage/residency/transaction、37项entity picking、all-building pick coverage、resource pool、terrain shader以及两项悬浮残片专用校验均通过。证据见 [发布记录](source-evidence-v4/published-stage-u69-hall11-cleanup.json)、[运行报告](source-evidence-v4/ivillage-remnants/hall11-runtime-cleanup-4317-final-u69.json)和[清理说明](source-evidence-v4/ivillage-remnants/hall11-level-independent-cleanup-u69.md)。

本次只关闭已定位的Hall XI v1/v2/v3可见残片。G39仍未完成：Hall X–XIII全邻域还需要从多方向、俯视和低角度扫描；Hall II完整采集因浏览器资源压力未完成；竣工后地面、道路、树冠、贵宾宿舍/水云轩范围以及全校全LOD直接点选仍是独立未完项。创科楼审计图中的白/青盒状结构经射线检查不属于创科current-form GLB，命中旧源tile，缺少可安全删除的正证据，因此本轮没有盲删。

## 2026-09-07 U60–U67 原子更新与“永远不清楚”根因

固定4317已原子切换到快照 `20260906T210638022343Z`，首页入口为 `index-BJEWiXo3.js`，应用逻辑为 `page-CnCbRGaG.js`。运行服务器实际返回的两份chunk、原生83-owner清单、实体registry、Hall X–XIII、创科楼与Hall II连廊模型/manifest/遮罩均与工作区逐字节相同，见 [HTTP发布核对](source-evidence-v4/current-form-live-http-u67.json)。TypeScript、定向lint、生产构建、registry、current-form事务/驻留/遮罩、原生细节规划/预算/稳定性、Hall II结构、飞行、三语与标签滚轮检查通过。

U67确认了一个真实状态机硬限制：`partialSlots`原本只有16个。它们是CPU端用于重建单张R8 `partialCoverage`联合遮罩的逻辑owner槽，不是16个额外shader采样器；旧实现让第17个及以后的可见原生owner即使有high/fine清单且完整组预算足够，也无法取得遮罩槽，因此“靠近、停留仍不清楚”。现已扩至96个逻辑owner，shader仍只采样一张联合遮罩。83/83个生产owner离线证明可请求high和终端fine；真实Hall XIII视角一次驻留27个原生owner并启用27槽，离开至Hall II再返回20秒后为26槽，加载/纹理/网格失败均为0。升级时先保留旧完整表示，只有新几何与新联合遮罩峰值预算同时满足才原子提交，避免基线闪回。

Hall II旧摄影最高层本身仍含封闭侧墙与缺口，不能靠增加owner修复。新current-form连廊模型以整段74.6m范围替换屋面/底板竞争源，含开放侧、斜撑、门框和透明屋面带；逐像素遮罩只在 `y=60.0–71.2` 生效，桥下约`y=48`坡面保留。真实画布直接点击模型命中 `space:ug-hall-2-covered-corridor`，见 [近景截图](screenshots/v4/u64-live-hall2-corridor-close.png) 和 [运行记录](source-evidence-v4/live-runtime-u63-u67.json)。

Hall X–XIII现状整组与创科楼已经进入同一current-form视距、屏幕占比、完整包预算、退出宽限和缓存恢复生命周期。Hall XIII近景可见低饱和蓝灰光伏分格和固定受光，未再看到用户截图中的贯穿多层悬空旧条带，见 [Hall XIII近景](screenshots/v4/u67-live-hall13-close.png)。切到Hall II时iVillage成为`inactive-cache`，返回即恢复`resident`，没有先露出旧施工楼体。无Pointer Lock的headless浏览器中，自由飞行已验证鼠标不按键移动即可改变朝向，W沿当前朝向移动；系统允许Pointer Lock时仍走原生捕获，Esc释放。

**U62仍未完成。** LandsD当前T12-NW-A 0.25m TDOP实际捕获日期为2025-01-11，与已有像素完全相同，仍记录iVillage施工期；HKUST 2026竣工照片只能支持局部材质/空间关系，不能可靠给出完整道路、平台、庭院和运动场边界。因此本版没有把缺乏依据的宽地面板强行发布，截图中Hall X–XIII周边施工纹理仍是明确待修项。全校园逐栋直接点选和逐区视觉验收也继续保持未完成。

## 当前优先：Hall X–XIII整组重建

用户U50明确要求完整重建四栋，G33已写入完整目标。080624已发布加载稳定性、83分区、原始地表保护与标签滚轮修复，真实页面已确认新源码、16采样器保护启用和292/292基础加载；不代表四栋重建或全校视觉已完成。此前已开页面需重新加载才能使用新源码。相机中心修复独立处理中。

## 用户要求总表与全楼点选未完成（2026-09-06）

已逐条回读原始任务及当前任务用户消息，完整33项验收要求写入 [GOAL.md](../GOAL.md)，原话见 [要求记录](source-evidence-v4/user-requirement-history.json)。用户最新再次确认仍有楼无法直接点选，G11/G12必须保持未完成：列表能找到、标签能点击、已有实体ID或少数源射线通过，均不证明所有实际楼体屋顶/立面可以正确点击。点选覆盖审计正在按所有实际楼、不同显示层及共享源分界逐项核对。道路/外观原有未完项继续执行，不被本次整理替代。

## 用户指出的连续道路与结构问题（优先修复）

用户新图明确要求 A/B–创科之间原道路、大学中心向海边通路、北门环形到巴士侧一起清楚，并保留隧道门洞及树冠/树荫的原结构，见[三图与要求](source-evidence-v4/user-road-structure-feedback.json)。当前只改善楼体的051654不能作全区通过，旧环境粗层和错误裁切均未修妥。

已分离的真实原因：

- 近楼借额使完整住宅123末叶域退出：该域688,718,740B（含原mask，不含union）与Tsang视角8外观合计超High1536MiB，需重新分区/保护连续环境的可见源，不能仅扩外观优先级。底部退粗块已按6条source ray确认属于Hall X屋面，不是DTM；报告当前在/tmp/hkust-tsang-regression/。
- A/B–创科道路对应6C12/17当前主hires缺少可用高组；其他缺失分支不应导致所有可用原树分支永久留在粗层。真实最高可用源补充与更小完整frontier正在准备。
- currentForms误删接近DTM的真实末叶非竖面，并与UG X真实源高度支持冲突；Hall ground/source protection正在修复。用户[缺面截图](screenshots/v4/user-reported-hall-gap.png)背景经嵌入ICC转sRGB后匹配场景sea-surface RGB65,102,111，确认上方表面缺失；并非恢复实体标签能解决。
- [源纹理SHA审计](source-evidence-v4/texture-reuse-audit.json)核824张实际图、671独立hiresGLB；当前Tsang/Lam潜在重复mip仅约32.45MiB，无法代替连续路廊分区与计划修复，未盲目假定GPU已共享纹理。

## 当前修复快照 051654（2026-09-06）

固定4317已原子更新 `20260906T051654980601Z`，类型检查、构建通过，[HTTP首页字节核对](source-evidence-v4/published-stage-051654.json)一致。实体/外观资产数量仍与231757相同；本次修改选择高亮、resize DPR同步及近距完整外观共享预算分配，不改楼源几何、纹理分辨率、总预算或8槽上限。

定向验证：选择5、UI12、motion41、quality6、新近距真实视角/边界/排空11、原pool9、加载46均通过；测试范围见[高亮报告](source-evidence-v4/building-selection-tests.json)及[预算报告](source-evidence-v4/near-exterior-budget-tests.json)。

真实同相机、1149×1079、High/DPR1.6复验：[A楼视角](screenshots/v4/fixed-tsang-near-high.jpg)保留A/B外观并恢复Academic；[B楼视角](screenshots/v4/fixed-lam-near-high.jpg)将原先两楼灰糊壳同时恢复为可见屋顶/阳台/窗列，邻近Academic保留。[B楼Ultra](screenshots/v4/fixed-lam-near-ultra.jpg)保持完整A/B。动态纹理实际值均在原cap内，观测error为空。**这只确认局部改善，不作全楼或全区通过。**独立对照发现A视角底部x535–715,y930–1079原浅色屋面/构筑物退成大三角，正在追实际源身份；不能都笼统归为地形。

## 前一快照阶段记录（2026-09-06 更新）

已原子发布完整快照 `20260905T231757226951Z`，固定 <http://127.0.0.1:4317/>。类型检查与构建通过；实际 HTTP 返回的 registry、外观清单及两份楼域与工作区字节完全一致，见 [发布核对](source-evidence-v4/published-stage-231757.json)。**真实浏览器视觉验收仍未完成，逐栋最终通过数为0；这不是声明每栋已失败，而是尚未完成所要求的全套对照。**

本轮新增与保留：

- 原生外观共 **47组/89源对象**：41组由建筑实体承载，6组为共同楼域（五个教职员宿舍域和VIII／IX共同域）；仍最多8组同时替换。共有4372实体/4749表示、54个building记录和14个zone。以上均不等于独立物理楼总数。7区域/13摄影前沿/671独立GLB与4套现状近似外观继续保留。
- 教职员宿舍5–19号的五个原生源组已绑定四个现有范围实体；15–19范围的两个真实楼域保留独立模型、遮罩和缓存，未造15栋坐标。见 [范围整合](source-evidence-v4/building-quality/staff-range-runtime-integration-qa.json)。
- 宿舍III补齐相同官方BUILDINGID的6A+6C跨图幅楼域，从596.094扩至1039.253平方米，原域保留、没有缓冲补造。海岸海洋实验室完整原生对象已安装，源投影外约32.620平方米仍保留baseline，未并入邻近体育源。见 [来源审计](source-evidence-v4/building-quality/remaining-native-source-audit.md)。
- VIII／IX共用一个官方物理域、一份完整原生对象和一份预算；整块源点击进入共同区域，可继续选两座原宿舍实体。两hall原ID、parent、楼层不变，不造第三栋楼、不按最近标签分楼、不套旧碎面索引。见 [共同归属回归](source-evidence-v4/building-quality/shared-halls-runtime-audit/qa.json)。
- 68条建筑/区域名称具备三语显示及原名搜索；设置统计改称“完整外观组”。集贤楼四柱/大厅照片候选已留为可审查资产，仍**未启用**；新逐像素审计否定了“正北树面截柱底”的旧视觉假设，短柱来自候选高度下界，大厅裁面未改善遮挡，见 [候选及误差](source-evidence-v4/building-quality/ggt-front-base-candidate/README.md)。

本轮必要验证：类型检查、构建、修改模块定向lint；registry验证640文件/95模型对象通过（只保留原UC电梯来源歧义提示）；HTTP加载生命周期17项、拾取34项、UI事务11项、实体三语7项、i18n6项通过。另有宿舍III补域12条角色回归、五Staff域15条真实源ray、VIII／IX完整3166面对象上的三条真实ray。数字分别记录，不重复累加成楼数或视觉通过数。共享组重复候选只预约23,017,252字节，少1字节则拒绝整组，最多8槽。旧全仓lint诊断未顺手清理，未声称全仓lint通过。

仍需处理的视觉与身份边界：

- **Hall XI–XIII**：旧真实近景明确出现旧摄影露出和PV压入灰屋面；第二轮资产已修遮罩下界和PV高度，仍待相同相机、反向及开层/合层真实复测。保留 [失败画面](screenshots/v4/halls-current-near-seam-failure.png)。
- **曾超生楼、林宝茹楼、大学中心**：已有旧近景能看清规则楼体，但新版共享预算下的反向、切区返回尚未验收。李家誠創科大樓照片纹理已实际进入模型，最终不受二次照明变暗的多角度材质复验仍待进行。
- **集贤楼、House1/6、校长宿舍、Staff1/3及Apartment1–12**：离线源图可见树木烘焙、平面简化或透视拼接，见 [逐图审查](source-evidence-v4/building-quality/northern-source-visual-review.json)。Apartment采样器修正两视图差异0，不能将灰条归因于clamp；这些图不是WebGL、地形或邻楼验收。
- **贵宾宿舍/水云轩**：现行服务名称与地图示意点已核实，但独立外观范围、入口及用途分区未确认；不能移用历史Tower C水云轩南座位置。医学大楼、NRB2、HPC5继续按建设阶段记录，未把计划效果图当作已竣工几何。
- 其他逐栋与六个共同域均在 [视觉验收表](source-evidence-v4/building-quality/visual-quality-status.md) 保留待验或受限原因；最终物理楼总数仍未确定。

运行与交互条件：三套动态mip工作集共享预算继续为Ultra2048/High1536/Balanced768/Smooth208MiB，取消解码需排空；CPU bitmap、固定纹理、几何与driver开销另计。此前出现过实际 `ImageBitmap could not be allocated` 和测试页崩溃，后续修复不能仅凭离线预算证明稳定。真实全幅PAN已留有限样本；普通/沉浸原生右键单击无菜单证据存在，但工具不支持原生RMB拖拽，不能冒充已验。

先前锁屏阻塞已由用户明确解锁并经CUA确认解除，原生goal恢复active；历史记录见 [阻塞审计](source-evidence-v4/preview-blocker-audit.json)。独立验收页恢复运行，用户原预览保留。真实Hall近景已见主立面/PV改善，但发现选中平面边界穿墙与关闭残留；切到A/B后发现完整组预算上限导致近邻回粗。以上有真实截图和状态，正在修复。全校goal保持未完成。

## 解锁后的真实页面复查（未修版 231757）

[桌面十视图审计](source-evidence-v4/resumed-desktop-browser-audit.json)记录了Hall XIII/XII、A/B、创科两面及LG/F开合。Hall主面与PV长带较旧失败图有改善，青线已定位为2D building drawing多环抬到同一source floor高度并穿透，不是摄影残片；关闭卡片只清React选择导致青线残留。选择修复已在源码，真实修后验收待后续快照。

[A楼Ultra实图](screenshots/v4/resumed-tsang-near-ultra.jpg)、[同相机High实图](screenshots/v4/resumed-tsang-near-high.jpg)、[B楼近景High实图](screenshots/v4/resumed-lam-near-high.jpg)揭示旧外观独立上限挡住邻楼；可出现High邻楼更清或A/B双粗。正在修同一共享池内的近楼整组分配，不降低Academic源质量，不增加总cap或8槽上限。

创科照片纹理在[正面](screenshots/v4/resumed-innovation-near-high.jpg)与[反面](screenshots/v4/resumed-innovation-reverse-high.jpg)实见；[LG/F](screenshots/v4/resumed-innovation-floor-open.jpg)正常打开，[收起后](screenshots/v4/resumed-innovation-floor-return.jpg)camera、target、quality、selected与空floorId均和打开前一致。仍有屋顶/立面近似限制，此项不等于全楼视觉通过。十份观测的三个加载器error均空、动态纹理pool peakOverCap为0；这不代表总GPU/CPU内存或长期稳定性。

[390px三语DOM复查](source-evidence-v4/resumed-narrow-trilingual.json)：三语canvas均从0,0覆盖实际CSS390×844，scrollWidth390、校徽40px，全部七个视角控件在横向范围内，实体与姿态不变。工具viewport override截图在缩小内容外附加留白，未把该截图当正常尺寸清晰度验收。临时viewport已reset、语言恢复简体。旧resize不会在DPR变化后刷新采样，已与选择修复一并在源码修正。

## 较早阶段原始记录

以下保留先前失败背景和测试细节；其旧数量与“待验”状态应以以上当前阶段记录为准。

## 全校逐栋质量主线

初步身份清点见 [named-building-inventory.json](source-evidence-v4/building-quality/named-building-inventory.json)：现有32条 canonical building 之外，33个有名称楼体候选仍藏在住宅区域聚合项中（Tower C/D、教职员Tower 1–19、House 1–8、Block P–S）。这是65条待核审计行，不是已确认65栋物理楼宇。Apartments 1–48不能直接算成48栋；Hall VI两命名塔体及Academic连续建筑内各命名翼需分别核对实际外观覆盖而不重复实体。

每栋须核实实际全立面与屋顶覆盖、当前完工外形、原生最高源、纹理尺寸和UV、自然近景加载及遮罩替换，再以与Academic相当的距离/角度/画质做真实多角度验收。原生摄影不足时按授权制作照片参考几何和材质，标明近似。最终逐栋通过表仍在制作，初表没有任何楼被提前标为视觉质量通过。

已复现的关键失败：

- [UG近景实际截图](screenshots/v4/ug10-terminal-near.png)与[state](source-evidence-v4/ug10-terminal-near.json)：最高档存在清晰摄影与前景粗块；37叶显示不代表相邻整楼最高覆盖。真实实体身份正在用相机射线核对，不能凭前后标签将粗楼误认作UG X。
- 当前37叶的真实官方域采样：UG X覆盖100%，UG XI仅31.93%，UG XII/XIII为0%。XI–XIII的细粗混合是覆盖缺陷；细源中的窗线/顶线波浪另有摄影几何失真，增加纹理mip不能修复。
- 用户曾超生楼、林宝茹楼与卢家骢大学中心的同角度对照已列优先样本。
- 创科大楼旧版41 mesh、6,797三角、无UV/贴图，当前正在实做官图参考纹理并绑定既有8层源几何，不再把纯色外形当完成。
- Hall XI–XIII的真实蓝/蓝灰陶瓷砖、圆角/折线形体、光伏折线屋顶有2026官图依据，不能一概称施工包裹或拉平成方盒。参考图的拍摄、导出、发布时间分列。

## 当前交互修正与证据边界

旧快照 `20260905T204154816837Z` 通过了独立canvas坐标验收，但其sidebar占位列破坏真悬浮，且沉浸瞬时改变canvas尺寸；用户已明确否决。旧viewport成功记录不代表最终交互要求通过。正在改为普通模式起整页全幅画布、header/sidebar真实悬浮，实际安全区域只偏移投影主点；同一300ms进度驱动四边UI平移与投影，快速切换连续反向，减少动态效果偏好可立即切换。

右键菜单根因已经确认：锚点PAN暂时设置`OrbitControls.enabled=false`，安装版OrbitControls的`onContextMenu`因此提前return，没有preventDefault。当前修复独立在canvas capture事件域阻止菜单，dispose匹配移除；地图外输入框与资料不注册此处理器。真实浏览器普通/沉浸右键单击待更新快照后验收。工具没有原生右键拖拽接口，不能声称测试了native RMB drag。

现有真实左键PAN证据（共用左右键锚点几何）：

| 样本 | 真实动作 | 无约束最大投影误差 | 边界 |
|---|---|---:|---|
| [中景地面](source-evidence-v4/anchor-pan-middle.json) | 80px平移 | 4.95e-11px | 10样本、0地面夹制 |
| [近景楼体](source-evidence-v4/anchor-pan-near-building.json) | 60/-20px | 3.60e-11px | 10样本、0夹制 |
| [较陡角度](source-evidence-v4/anchor-pan-steep-view.json) | 60/15px | 5.11e-11px | 10样本、0夹制 |
| [远景](source-evidence-v4/anchor-pan-far-first.json) | 100/30px | 3.14e-11px | 8夹制样本因防穿地发生最高5.36px偏差，单独记录 |

首次source三角拾取实测约18.7–31.7ms，不能将几何误差近零说成输入延迟为零。上述样本来自旧布局，新的off-axis全幅版仍需真实复核。当前同源组件回归39项，涵盖固定锚点/近地平线/防穿地、真实Orbit路由、轻点与往返拖动区别、右键菜单三种触发时序、丢capture/buttons、全幅off-axis射线/PAN、过渡中间帧/快速反向/姿态不变/reduced-motion；这是组件证据，不代替WebGL及原生鼠标菜单。

## 实体拾取与入口几何

目前有证据的拾取面域为25/32 canonical建筑：原18官方PathAdvisor域，加7栋官方iB1000闭合楼域与实名标注（曾超生、林宝茹、集贤楼、UG III/IV/V/VII）。20项回归、61条真实源墙/屋面射线覆盖25栋（50 baseline、11 fine）。源内带孔多边形与明确0.15m边缘点击容差，不用大包围盒归整摄影tile。剩余未绑定域与新发现聚合楼群继续处理，不能称所有楼已可点。

入口近景发现两个明确失败并已定点修改，真实新版截图待验：

- surface2的DTM+高度裁切错误切除低墙面，已限制到向上表面；源地面reference增加361个真实fine投影像元/90.25m²，均由原baseline兼容面验证，9个不兼容候选拒绝。原保护像元不变，源Y编码误差≤0.001944m。
- 入口舞台真实33/38/55面已与广场88面同实体拾取域；红鸟旧摄影主体遮住社区模型时，用实际主体三角投影+0.10m明确容差及Y123.145–131.645关联同canonical地标。无扩大方框、无穿透前景，不改变渲染。

入口车道派生资产来自51份error0源：70,304真实摄影道路三角+22,165 piazza DTM三角，合计92,469。覆盖确认道路域97.5281%；剩余129.8673m²保留baseline。跨源投影重复0.000593m²；同源多层34.40373m²保留，不能声称总零重叠。210,912道路顶点回源平面最大误差0.0000796m，712,800 TDOP像元保持。52360旧标签错误强绑已撤销；用户公交/的士/小巴事实仍只归入口区域，不能据此虚构线路对齐。

## 加载、画质与稳定性

当前最高资源包含7区域、13完整frontier、585独立GLB。数字是资产覆盖，不是已通过楼体数。最高mesh预算1792MiB、高清1024MiB；以真实mip估算和partial联合R8遮罩计预算，完整区域/楼栋原子替换并处理取消排空、缓存、重试。

[细节生命周期44项回归](source-evidence-v4/detail-loading-tests.json)通过。部分早期快照曾出现入口15次mesh失败、blob纹理错误并落到Smooth；另一次新Auto IAB页面崩溃，准确底层原因未完全归因，失败证据保留。后续确实修正了Ready事务残留GLTF parser/bitmap引用，并避免把初始化/上传当成稳态慢帧；Auto稳定后可按样本下调或恢复到硬件初始上限。

有限真实观测：`.202420` High与Ultra、`.203318`新Auto与入口四个fine组、`.204154`新Ultra均完成加载且mesh/exterior错误0。入口四fine共1,874,776三角、1,831,115,908B、1792MiB预算内；这不能证明全校覆盖或永不崩溃。新增全校源仍须按当前goal审查峰值与切区返回。

## UI、资料与来源

固定HKUST三语不变，官方校徽比例保留，窄屏最低40px要求已修源码，最终运行需复测。资源单入口：实体→相关资料→原图/全景→返回原资料→实体。

[红鸟照片返回实测](source-evidence-v4/resources-landmark-return.json)：2004-10-26原图日期保留，返回后camera/target/ID/floor/quality/语言不变，无幽灵面板。[窄屏三语言](source-evidence-v4/narrow-trilingual-final-stage.json)旧布局CSS390px无横向溢出，语言不改实体/姿态；新版真悬浮布局须再验。UI事务回归9项，i18n6项已通过；组件不代替最终真实照片/全景/楼层返回。

创科楼源floor Z131.95–166.95m，上部+5m是示意延伸，不是屋顶测量。红鸟为MIT社区源按官方8.5m高度校准：29,064源三角+64参考细杆；不是官方CAD或实测方向。原始来源、日期与派生说明随资产保留。

## 当前剩余工作

1. 原子发布并实测右键菜单、全幅真悬浮、同进度四边沉浸/恢复、off-axis PAN和实体点选。
2. 入口两处实际失败的新版近景/拾取验收。
3. 创科楼纹理进入模型、多角度近景和打开楼层验证。
4. 完成全校实际命名楼宇清单与逐栋质量提升；Hall XI–XIII、曾超生/林宝茹等用户失败样本不能留在仅研究或待建议状态。
5. 全校新版最高/Auto加载与资源安全、三语/窄屏/室内/资源返回的最终真实检查，以及与最终同源的适当回归。
