# HKUST 清水湾校区：已获取地理资产

核验日期：2026-09-05。全为香港政府公开数据，只读下载，无账号注册。范围是8张完整政府图幅及周边缓冲，不是法定校园边界。

## 立即使用

- `tileset.json`：8图汇总 Cesium 3D Tiles 入口。经路径递归检查：169个可达JSON、292个b3dm、198894180字节几何纹理，引用完整。结果 `validation.json`。
- `mesh/<tile>/tileset.json`：逐图入口。
- `dtm/*.tif`：6图 CEDD 2020 LiDAR 原始 0.5m GeoTIFF；东侧额外 DTM 由实施任务准备。
- `bit00/11-NE-10D/`、`bit00/12-NW-6C/`：2026最新发布包实际解压的逐栋 FBX/.att/JPG。原 ZIP 也保留。`attributes.json`汇总521条 .att 原文。
- `coordinate-checkpoints.json`：校园16个 HK1980 网格控制点，经政府 API 转 WGS84及椭球高，可用于水平投影/高程实现回归。

## 8图范围

西列：11-NE-10B、11-NE-10D、11-NE-15B。
中列：12-NW-6A、12-NW-6C、12-NW-11A。
东侧海岸补幅：12-NW-6D、12-NW-11B。
每图750m×600m。核心六图：HK1980 E=844250..845750, N=821000..822800；东部海岸补幅向E=846500延伸，范围 N=821000..822200。

## 真实几何与精度边界

三维来自政府倾斜航摄影像产生的mesh，建筑、树木、道路、山坡往往粘在同一mesh，不能保证单栋分离或室内。模型保留原几何和纹理二进制字节，没有自行创造建筑与山体。
为了下载/交互体积，本子集在原始geometricError <=7m处取一个完整LOD前沿；这不是7m测量精度。少量官方JSON引用ZIP中不存在的 *_1.b3dm，因此回退到最近可用祖先原始mesh，覆盖保留，但这些局部比目标LOD更粗。
原JSON错误地把12元素盒体写成boundingVolume.sphere，本子集改为box，12个值不变。顶层包围盒改为原子盒体并集。保留 `source-tileset.json`用于追溯。
只取一个前沿意味着这些本地tileset不再能放大到原始最高LOD；原zip索引含offset和大小，能按Range继续提取更细LOD。`prepare_source_subset.py`是可重跑的原准备脚本（脚本默认六图，东两图另调用prep_tile函数）。

## 时间：不可把发布日期当成实景拍摄日

- Photogrammetry数据集全局metadata revision为2026-08-28，但本次8幅的REVISIONDATE为2025-03-27；已实测12-NW-6C.zip Last-Modified为2025-03-20。均不保证拍摄日期就是该日。
- DTM源航空LiDAR采集期2019-12-20至2020-02-02。对2020后新建楼周边整平地形需要校方最新资料补充。
- 3D-BIT00图幅索引：11-NE-10B revision为2026-06-01；其余核心5幅为2026-04-01。下载两图的ZIP Last-Modified为2026-08-27。然而逐栋 .att 仍含2010/2015/2021等旧日期；地形 .att 有20260827和20250101。不把它们误称整栋2026重测。

## DTM坐标与像元

Pillow直接可读Float32 TIFF，NoData=-9999。分辨率0.5m，1500列×1200行，PixelIsArea。使用GeoTIFF tag33550像元尺寸与33922 tiepoint。例12NW6C左上角E=845000,N=822200；像元(r,c)中心为E=845000+(c+0.5)*0.5,N=822200-(r+0.5)*0.5。
水平为HK1980 Grid / EPSG:2326。应使用正式投影库的2326→4326并显式XY顺序，不做经纬度米制近似。
垂直为HKPD；Cesium等采用椭球高。政府实测转换：E=845000,N=822200,HKPD=0 → lon114.261638616,lat22.338847842,ellipsoid=-2.371m。该偏移在校园各点略变，16点见coordinate-checkpoints.json，不要把HKPD直接当椭球高。官方工具说明采用HKGEOID2016_SMO。政府mesh已在ECEF放置，子tileset transform包括ECEF平移，不应再次套HK1980水平变换。

## 数据入口与许可

1. 三维瓦片官方metadata
https://portal.csdi.gov.hk/csdi-webpage/metadata/landsd_rcd_1671677054006_62261/html

2. 三维索引查询（返回Format_3D_Tiles/OBJ公开下载链接，含官方提供的公共下载key）
https://portal.csdi.gov.hk/server/rest/services/common/landsd_rcd_1671677054006_62261/FeatureServer/0/query?f=geojson&geometry=114.25,22.325,114.275,22.345&geometryType=esriGeometryEnvelope&inSR=4326&spatialRel=esriSpatialRelIntersects&outFields=*&outSR=4326

3. CEDD LiDAR metadata
https://portal.csdi.gov.hk/csdi-webpage/metadata/cedd_rcd_1629267205233_87895/html
对应FeatureServer/0=DTM2020，/1=DSM2020，几何查询参数同上。

4. 3D-BIT00
https://portal.csdi.gov.hk/csdi-webpage/dataset/landsd_rcd_1637306559892_42396
对应FeatureServer/0图幅索引，提供FBX/3DS/MAX/VRML。

5. 坐标/高程API官方手册
https://www.geodetic.gov.hk/transform/v2/tformAPI_manual.pdf
https://www.geodetic.gov.hk/en/services/tform/tform.aspx

6. 使用条款
https://portal.csdi.gov.hk/csdi-webpage/doc/TNC
允许免费浏览、下载、分发、复制、链接与打印，含商业和非商业用途，需明确标识香港政府与来源网站并承认数据知识产权。建议应用常显：
“3D Visualisation Map from Lands Department; LiDAR DTM from Civil Engineering and Development Department, Hong Kong SAR Government.”
另保留源链接、数据日期与子集处理说明。API在线streaming另外可能需专属免费key；本离线ZIP数据不需要申请。

## 校方二维/室内资料和政府室内缺口

HKUST官方地图下载入口（页面当前图片路径2026-08）：
https://mtpc.hkust.edu.hk/resources/campus-location-maps
可取PDF/JPG/AI，Campus_Map_Color_OL.zip与Lecture_Theaters_OL.zip是公开AI包。地图和室内图片应保留校方来源，不能把政府开放许可扩展到校方版权。
https://publish.ust.hk/univ/maps/Campus_Map_Color.pdf
https://publish.ust.hk/univ/maps/Lecture_Theaters.pdf
https://campus-vr.hkust.edu.hk/

政府3D室内API实测venue_polygon全表689个venue；校园bbox无空间交集，名称也无HKUST。不得声称政府有该校园完整室内模型。
https://portal.csdi.gov.hk/csdi-webpage/apidoc/3d-indoor-map-api
