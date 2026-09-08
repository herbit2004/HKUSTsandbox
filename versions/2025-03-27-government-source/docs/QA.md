# 验证记录

第二轮优化的当前验收与对照截图见 [QA-v2.md](QA-v2.md)。以下保留首轮记录与当时计数。

验证日：2026-09-05，macOS，本机127.0.0.1:4317，Codex内置浏览器。

## 数据与坐标

- 地形：108,412个GLB顶点全部逐一映回原始TIFF，高度差最大0m；源缺失值未补造。见public/terrain/independent-qa.json。
- 摄影网格：292片源资产、引用与b3dm头长度合法；328万三角形。分块局部矩阵相对非线性PROJ抽样最大误差0.00129m。见public/models/validation.json、preview-validation.json。
- 预览纹理降采样保留所有几何buffer原字节，约139.4MiB；原纹理GLB约189.7MiB。没有宣称手机性能或精确帧率。
- 点位：34个独立点，其中18官方轮廓中心、6 SEN/VR参考、10示意图配准。地图配准独立交叉验证RMSE29.62m、最大49.93m，保留约50m提示范围。
- 室内：78层原公开GeoJSON完整保留9951源要素/9955多边形部分，63层CAD约164万线段。背景要素名称为空且不可点击，未删除其公众可见几何。LSK6F多Z不压平。见public/interiors/validation.json和cad-validation.json。
- 更新包络：5栋GLB只有侧面与已知Z高度线，无臆造屋顶/底板，Z未超源范围。见public/updates/independent-qa.json。

## 构建与浏览器

- TypeScript `npx tsc --noEmit`通过。
- `npm run build`通过，生成dist/client静态构建；有Three.js主包体积提示，不是构建失败。
- 真实校园全部292片载入；未发现本轮浏览器error。最终总览截图overview-final.png。
- 主楼G→1F切换；输入LTB仅返回LTB，点击后聚焦正确阶梯教室，能见源CAD座席/门扇。截图indoor-ltb-final.png。
- 1F全景点1→点2可沿真实连接移动，拖动旋转正常。截图panorama-corridor.png。
- 开启联网全景，筛选Shaw G及Lee Shau Kee Business Building G，均成功GET并球面显示；相邻节点按钮来自源边。截图panorama-shaw-online.png，panorama-lsk-online.png。

- 最终版搜索Hall X仅保留匹配标签，点击宿舍10座后定位成功；2026包络实际显示，室内入口/照片与资料提示一致。截图updates-hall-x.png。
- 可独立关闭外观检查LiDAR山坡，恢复外观后启用160m高程剖切，均已目视。截图terrain-only.png、section-160m.png。
- 2026.08官方校园原图模态正常打开，原图实际载入2024×1432像素，并提供本地PDF原文件链接。
- Shaw G层73个公开多边形与座席CAD、真实室内照片同时显示；叠看4层共246个多边形正常。截图indoor-shaw-photos.png。
- 修正模型初始载入前更改筛选/图层的状态同步，最终TypeScript检查与静态构建均通过。构建预渲染须允许本地端口监听。
- 独立只读复核确认README、覆盖清单、公共数据与dist/client主要计数及引用一致；照片74条关联对应41个独立资产。

截图保存在本目录screenshots/，数据完整性检查结果为data-validation.json。未执行手机设备的性能与触控验收。

## 未作出的承诺

未把虚构层高、示范家具、旧外观、照片上传日包装成最新竣工实测；未验证每一个联网全景，未验证每个实体房间当前开放状态；未生成可信全校园无障碍/最短路径网络。校园模型用于浏览和认路，不是工程BIM或施工测量依据。
