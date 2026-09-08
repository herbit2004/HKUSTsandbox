# HKUST Path Advisor：公开室内真实矢量与全景元数据

获取日期：2026-09-05。官方新版： https://navigate.ust.hk/path/app/ 。接口均来自该公开页面实际引用的 `main.c4c44c26.js`；脚本 Last-Modified=2026-08-22，GET无需Cookie、Authorization或登录。未访问管理端、测试站点、登录服务或内网。

## 交付入口

- `manifest.json`：全套元数据、来源URL、HTTP状态/日期、SHA-256、每层文件与计数。
- `coverage-summary.json`：19栋建筑覆盖摘要。
- `all_base_map.geojson`：官方19栋校园底图轮廓；含新Innovation Building与UG Hall X–XIII等。
- `building-floor-catalog.json`：19栋、78个官方公开楼层ID、名称、elevation序号、show_in_path_advisor状态（本次78层全为true）。
- `floors/<building_floor_id>/rooms.geojson`：真实房间/空间多边形，共9951个；不是9951个独立房间，一些是楼梯、井、走廊、墙边空间或建筑细部。
- 同目录 `cad-lines.geojson`：63层有官方CAD线稿；Academic 1F含48507条源线段。原文件保留，无坐标猜测。
- 同目录 `nav-nodes.json`：共4385个官方房间/设施导航点；节点本身不等于完整可路由走廊图。
- 同目录 `point-of-interests.json`：共88个官方POI。
- 同目录 `floor-plan.svg`：78张完整北向矢量平面，直接由上述房间多边形/CAD生成，不需要拼旧地图截图。全部SVG XML解析有效；浏览器视觉验收由实施任务执行。`svg-index.json`提供路径。
- 同目录 `public-panorama-nodes.json`：共2044个visibility=visible_to_public的官方全景节点、坐标、校正偏角、照片URL与源时间戳。
- `public-panorama-graph.json`：2044公开全景节点与2116条官方连接边，已按官网逻辑建立双向邻接；所有边的端点都在公开节点集合中。图有135个连通分量、59个孤立点，不能假称全校园连续任意漫游。
- `validation.json`：结构与完整性核验结果。

所有原始响应以 `*-response.json` 保留，处理后的文件单独写出。无需重复下载。平面/矢量与原始响应有一定重复，总目录约数百MB；运行时可只带rooms、简化线稿、节点及少量全景样片。

## 覆盖

| 建筑 | 已返回公开楼层 | 空间多边形 | 公开全景节点 |
|---|---|---:|---:|
| Shaw Auditorium | G, 1, 2, R | 246 | 68 |
| Academic Building | LG1, LG2, LG3, LG4, LG5, LG6, LG7, G, 1, 2, 3, 4, 5, 6, 7 | 6750 | 1211 |
| Cheng Yu Tung Building | G, UG, 1, 2, 3, 4, 5, 6 | 555 | 162 |
| HKUST Jockey Club Institute for Advanced Study/Lo Ka Chung Building | G, 1, 2, 3, 4, 5 | 324 | 200 |
| Lee Shau Kee Business Building | G, 1, 2, 3, 4, 5, 6, 7 | 886 | 282 |
| Lo Ka Chung University Center | G, 1 | 118 | 22 |
| UG Hall I | G, 10 | 101 | 16 |
| UG Hall II | 11, G | 81 | 4 |
| Tsang Shiu Tim Sports Centre | 2, 3, 4 | 60 | 0 |
| Coastal Marine Lab | G, 2, 3, 4 | 73 | 0 |
| Li Dak Sum Yip Yio Chin Kenneth Li Conference Lodge | 2 | 30 | 0 |
| Outdoor Swimming Pool | G | 21 | 0 |
| UG Hall X | G, 7, 10 | 122 | 0 |
| UG Hall XII | G, 7 | 51 | 0 |
| UG Hall XI | G, 1 | 28 | 0 |
| UG Hall XIII | G, 7 | 140 | 0 |
| Martin Ka Shing Lee Innovation Building | LG, UG, 1, 2, 3, 4, 5, 6 | 286 | 79 |
| Water Sports Center | G, 1, 2, R | 42 | 0 |
| UG Hall VI | G | 37 | 0 |

## 版本差异与真实缺口

旧Path Advisor浏览菜单曾列Academic LG7/LG5/LG4/LG3/LG1/G/1–7；新版接口实际另外给出LG2与LG6（分别只有4与42个空间多边形）。不能据这两层的数据量臆测其它未列房间。
旧菜单曾列CYT到7/F；新版返回G、UG、1–6，仅按已发布8层展示，不编造7/F。
宿舍只拿到公开返回的少量楼层。例如UG Hall X为G/7/10，不能把这3层复制成完整宿舍内部。
唯一房间导航接口业务缺口：UG Hall XI G 的nav-nodes返回meta404“Navigation Nodes not found”；该层6个多边形可用。
有78层平面但只有63层CAD，不填造其余CAD。只有返回公开全景节点的楼层才应提供对应照片漫游。

## 坐标、层高与显示规则

房间多边形、CAD、导航点、全景点已是经度/纬度坐标，官网直接交MapLibre使用。无需从旧png上手工配准。
房间GeoJSON多数坐标带Z；原始Z应逐顶点保留。例如Academic G=123、1=127、2=130.725、3=136，真实层距并不完全相同。catalog的elevation字段却是楼层序号（如1、-1），不能误当米制海拔。
**Z垂直基准与量测精度未从公开接口文档核实**。它们高度值与建筑绝对楼层高度相符，但在政府DTM/三维外壳中使用前仍需验证整体基准差。LSK 6F在同一层包含168.4、172.6、176.8、181多种Z，不能把整层强行压平。
房间属性 `hidden_from_map` 按官网规则保留，供应用抑制对应名称/详情标签；不可擅自为这些空白或隐藏要素补名字。本次5653个空间要素为hidden_from_map=true。
经纬度小数位很多不代表测量达到对应精度，来源没有公布可据以保证的米级/厘米级误差。

## 全景照片接入

本阶段仅批量获取元数据，不批量下载照片。示例公开照片URL：
https://navigate.ust.hk/path/api/app/assets/panorama/id?id=69cd366ac5a78a07e3342333
GET实测200、image/jpeg；读取JPEG头确认3840×1920，2:1全景。HEAD却返回JSON，不能据HEAD判不可用。证据 `sample-panorama-format.json`。

官方JS的方向校正：
- sphereCorrection.pan = 180 - (pan_offset || 0)，单位度。
- sphereCorrection.tilt = tilt_offset || 0。
- sphereCorrection.roll = roll_offset || 0。
- gps=[longitude, latitude]。
- panorama_edges按双向邻接，但只连接公开nodesMap中存在的节点。

节点created_at/updated_at是元数据时点，不保证照片拍摄日期。原始完整响应保留；运行时public-panorama-nodes文件已删去与认路无关的creator/updater内部ID。

官方街景页面可用同一个已公开节点ID进入（由公开JS路由逻辑确认）：
https://navigate.ust.hk/path/app/street-view?id=69cd366ac5a78a07e3342332&building_id=b00000000000000000000001&building_floor_id=bf0000000000000000000108

## 实际公开接口

接口前缀 https://navigate.ust.hk/path/api 。以下路由均在官网main JS中实际调用；楼层/建筑ID均从官方返回值读取，未猜测或枚举私有ID。

- `/app/assets/all-base-map`
- `/app/locations/building-floors?building_id=<公开building_id>&limit=50`
- `/app/building-floors/geojson?building_floor_id=<公开floor_id>`
- `/app/building-floors/nav-nodes?building_floor_id=<公开floor_id>`
- `/app/building-floors/point-of-interests?building_floor_id=<公开floor_id>`
- `/app/panorama-nodes?building_floor_id=<公开floor_id>`
- `/app/panorama-edges?building_floor_id=<公开floor_id>`

采集每阶段最多2个并发请求，新增响应后暂停0.25秒，使用GET、无登录信息。

## 归属与许可

这些是HKUST官方公开校园地图数据。保留“HKUST Path Advisor / Hong Kong University of Science and Technology”、源URL、获取日及派生说明。本次没有找到允许任意对外再分发的明确开放数据许可，因此不能把香港政府CSDI开放许可套用于校方数据。当前用途是用户授权的本地校园学习/认路模型。
