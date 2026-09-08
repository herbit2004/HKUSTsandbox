# HKUST 清水湾认路标注点

`hkust-pois.json` 是可直接读取的 34 条对象数组，`id` 与 `hkust-buildings.json` 中原始名称记录匹配。它提供标签位置，不生成或假设建筑外形。

坐标为 EPSG:2326 / HK1980 Grid；Three.js 使用原点 E844800/N820500，`localX=E−844800`、`localZ=−(N−820500)`。高度应另外从真实地形或有证据的楼层数据取得。

## 来源优先级

1. **18 点：官方 Path Advisor 地理底图轮廓中心。** 来源 `https://navigate.ust.hk/path/api/app/assets/all-base-map`，本地原始文件 `/tmp/hkust-pathadvisor-complete/all_base_map.geojson`。先投影为米制坐标，再按面积加权计算 Polygon/MultiPolygon 的中心，内环扣除。新取得的该数据已替换相应手动配准点，包括 Shaw、CYT、Innovation、LSK、IAS、Hall X–XIII 等。原参考点只保存在 `supersededReference` 供审计，不应同时渲染。
2. **6 点：官方 SEN/VR 地理参考点。** 图书馆、Hall VII、Hall IX 使用官方 SEN 地图点；Atrium、Piazza、Fok Ying Tung Sports Center 使用官方 VR 场景坐标。它们是设施、附近坡道/停车位或全景相机位置，不是入口或建筑中心。
3. **10 点：Aug2026 校园图人工取点及仿射配准。** 使用可见建筑轮廓内的代表点，具体像素、描述及来源均保存在记录中。仅供浏览认路，建议显示“地图估计位置，约 50 米提示范围”。

官方地理数据没有公布测量精度和完整几何采集日期，所以相应 `accuracyMeters` 为 `null`；此 null 不能在 UI 中解释为“零误差”。手工配准记录中的 `accuracyMeters=50` 是保守认路提示半径，**不是测量或统计精度保证**。

## 配准与验证

官方校园 PNG 为 2024×1432 像素，标题 `Campus_Map_ColorC&E_Aug2026_OL`。11 个 SEN 设施对应点的仿射拟合 RMSE 为 **18.876 米**、最大残差 **29.3 米**；留一验证 RMSE **25.407 米**、最大 **39.807 米**。这些是人工设施对应的一致性残差，不是测量控制点残差。

取得 Path Advisor 后，另把先前已取点的 9 座建筑与官方轮廓中心独立比较：RMSE **29.62 米**，最大 **49.93 米**。比较后未重新拟合，也没有追加手工点；对应建筑全部已改用官方地理轮廓中心。详情见 `hkust-poi-registration-crosscheck.json`。

- `hkust-poi-registration.json`：完整 11 控制点、原始 WGS84、地图像素、残差与仿射矩阵。
- `hkust-poi-map-audit.png`：橙色十字为 SEN 对应控制点，蓝圈为最终仍保留的 10 个人工地图点。
- `hkust-poi-coverage.json`：已定位与未定位列表。75 条原记录包括楼内命名空间、分翼和合并的多楼记录，不代表 75 座独立建筑。
- `hkust-poi-qa.json`：34 点 ID 唯一、坐标有限、全在地形子集矩形内、最近 5 米采样点均有有效 DTM 高程。
- `build_hkust_pois.py`：可复现处理脚本；Python 3 + NumPy + Pillow + pyproj。

查证日期：**2026-09-05**。校园图更新为2026年8月；SEN 历史点和 VR 元数据未公开修订/采集日期；Path Advisor 当前公开接口获取日期不等于竣工测绘日期。POI 和校园图不能作为自动导航路网、门禁许可、精确入口或竣工建筑轮廓使用。
