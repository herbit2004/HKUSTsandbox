# V3 统一校园沙盘验收

验收日期：2026-09-06（香港/上海时间）。本地预览：http://127.0.0.1:4317/ 。本轮没有发布、提交或合并。截图为真实浏览器画面，以下只把实际检查过的视角和流程标为通过；早期失败截图保留作诊断，不能作为最终通过证据。

## 实际交互与画面

|检查|结果与证据|
|---|---|
|主界面|统一校园场景、搜索、实体树、楼层工具；顶部原口号/介绍卡已移除。没有三档画质按钮或独立外观查看器。|
|主学术大楼多角度|实际选楼后37个源对象完整驻留，原纹理基础RGBA估算479MiB。旋转并缩放后另一侧仍为同一37对象组，没有逐片先清晰的半栋切换。截图：[第一角度](screenshots/v3/academic-exterior-angle1.png)、[第二角度](screenshots/v3/academic-exterior-angle2.png)。|
|郑裕彤楼多角度与楼层|2个源对象完整载入，基础纹理约34MiB；两角度均保留全楼。G/F原位显示18个空间、8个实际层名（含UG/G），校园仍在。截图：[第一角度](screenshots/v3/cyt-exterior-angle1.png)、[第二角度](screenshots/v3/cyt-exterior-angle2.png)、[G层](screenshots/v3/cyt-interior-world.png)。|
|Shaw外观、楼层及脚下地形|独立整组外观；打开楼层隐藏真实源外壳投影，周边有源DTM恢复，不再出现蓝色水洞。最终图：[恢复DTM](screenshots/v3/shaw-dtm-restored.png)。真实粗细GLB的shader缓存回归见[JSON](source-evidence-v3/terrain-shader-cache.json)。|
|体育场与地表|全局摄影覆盖优先于DTM。跑道、足球场和2个网球面使用真实原边界、原正射影像、源地形；未抬高面片。跑道1229个有效同点样本中95.61%旧DTM高于摄影，足球场1656样本中99.879%高于摄影，解释旧绿色覆盖。最终场地与海面见[真实画面](screenshots/v3/sea-edge-color-matched.png)、[源面QA](source-evidence-v3/surface-qa.json)。原影像的树影/暗纹继续保留。|
|海面矩形色差|最终背景色取原摄影远海纹理，限定远离官方岸线的低海面有效范围淡出。相同视角上下原接缝RGB距离约170降至0.023/0；22,065个保护区域像素均在每通道3容差内。此为JPEG画面比较及显示色接修复，不是新测量或所有角度无缝证明。[最终像素报告](source-evidence-v3/sea-edge-final-pixel-qa.json)。|
|空间/CAD同坐标|Shaw G01、主楼LTB原位选中并显示源CAD；边界示意高度0.8→1.2m后CAD锚点不变。[LTB](screenshots/v3/academic-ltb-world.png)。相同来源多Z保留，未给未知墙高伪造实测值。|
|地下层电梯|LIFT14实际显示7/6/5/4/3/1/G/LG1/LG3/LG4/LG5停靠，未推造2/LG2。LG5源Z=102.62m，改为从实际电梯位置上方取景，实体可见；继续拉近至相机110.74m仍在合法楼层内。截图：[LG5最终](screenshots/v3/academic-lift14-lg5-final.png)，[有限相机视线检验](source-evidence-v3/lg5-overhead-ray-check.json)。|
|相机防穿地|实际球场拖动、最大缩放、12次方向键平移后，1m源地形12.26823m，相机14.077m，净空1.80889m。每帧约束后继续渲染，无地下轨道。真实LG范围允许低于室外DTM，范围外仍约束。截图：[净空](screenshots/v3/camera-ground-clearance.png)。|
|道路直接点击|最终构建中先搜索University Road，再关闭实体卡，直接点击画面桥段[991,560]，恢复相同`path:universityroad`卡与树选择。不是仅列表点击。源中心线的DTM高度仅作显示参考；桥面实高未知。[截图](screenshots/v3/university-road-canvas-click.png)、[状态](source-evidence-v3/road-canvas-click.json)。|
|照片/全景与返回|Shaw G01照片→返回、附近全景→返回已实测，前后entity/floor/camera/target/CAD锚点一致；[照片](screenshots/v3/shaw-room-photo.png)、[全景](screenshots/v3/shaw-panorama.png)。类型收尾时实际发现6个cube全景没有单asset地址，已改为校验原六面地址，防止拒绝整张2091资源表；最终构建另复测照片对话框，见下方补充记录。|

“shaw-interior-final.png”“academic-lift14-lg5.png”“sea-edge-on.png”等早期文件保留了实际失败；最终结论分别以`shaw-dtm-restored.png`、`academic-lift14-lg5-final.png`、`sea-edge-color-matched.png`为准。

## 数据、回归、构建

- `npm run check`：退出码0，整个TypeScript项目通过。
- `npm run build`：退出码0；静态首页预渲染完成，[构建日志](source-evidence-v3/final-build.txt)。预览实际加载的是`dist/client`。
- `python3 scripts/validate-registry.py --project . --report docs/entity-validation-v3.json`：退出码0，4,348实体、4,680表示、4,301可交互房间部分、8整栋组、48个模型（47外观对象+1运动场GLB）、374资产文件、704停靠、4场地、56道路代码组、223条源段。[报告](entity-validation-v3.json)。唯一warning是来源UC位置标识冲突，已按相距38.556m的两个位置拆分，未掩盖原始歧义。
- `node scripts/check-camera-ground.mjs`：退出码0。1021个实际5m三角比较最大差0.000445898m；真实1m样本最大差8.24e-13m；300帧阻尼高度漂移0；NoData、坡脊、孔洞、LG、多Z约束均通过。[报告](camera-validation-v3.json)。
- `node scripts/check-runtime-races.cjs`：退出码0，9项延迟/取消/资源回归通过，包含旧楼层不会恢复、单个在途GLB解码、原纹理迟到绑定与清理；[日志](runtime-race-validation-v3.txt)。
- `node scripts/check-terrain-shader.cjs`：退出码0，使用真实GLB与Three程序key验证粗细地形互斥及Shaw恢复DTM。DTO引入后两脚本加载真实`source-types`，不是空stub。

## 源代码 lint 的实际边界

新增/重构的10个主模块及2个验证脚本按原`.oxlintrc.json`规则检查，退出码0、0诊断，未关闭`no-explicit-any`或React规则。[命令记录](source-evidence-v3/new-source-lint.txt)。新边界采用DTO与unknown校验，检查了真实78层、9955个全部room parts（含5654个背景center=null）、23个footprint及4348实体；LSK6F的整体z=null不压成数值。照片和六面全景分别按真实资源形态读取。

`npm run lint`仍退出码1：24个维护文件中，7个旧文件合计126个error。本轮未将旧基线冒充通过：

|旧文件|诊断数|
|---|---:|
|app/indoor.tsx|48|
|app/panorama.tsx|41|
|app/detail-stream.ts|16|
|app/mesh-detail.ts|10|
|app/standalone.tsx|9|
|app/resources.ts|1|
|vite.config.ts|1|

详见[完整机器报告](lint-baseline-v3.json)。主要为旧`any`、React compiler/hooks、旧异步调用及可访问性规则。按授权仅将`source-*/**`第三方归档、`public/**`原始/生成资产、未引用的`components/ui/**`和`hooks/use-mobile.ts`起始模板排除扫描；维护中的`app/**`及scripts继续扫描。第三方源文件未修改。

## 已知限制

只有8个核实建筑具备完整独立最佳外观组，其余仍使用真实摄影与整区域纹理；未承诺所有建筑具备同样的源细节。主楼纹理量较大，479MiB仅为基础RGBA，不含mipmap与其他GPU资源。公开地形、摄影、建筑包及室内平面年份和垂直基准不一致；1m采样间距不是测绘精度。

56个道路组包含有源定位的周边道路，未把所有道路都登记为校内；隧道不伪造地面线。道路通行权限、门向、墙高、精确桥高和完整路网拓扑仍未知。照片与附近全景关系不等于精确房间拍摄。本轮测试没有逐一人工检查2050个全景、全校每间房或每种设备/屏幕尺寸。

## 最终资料回归补充

最后构建的独立浏览器页成功解析2091个资源条目，Shaw五张照片列表显示正常；打开原Main Hall照片后对话框完整覆盖页面，再关闭照片与资料面板，前后entityId、floorId、camera、target、CAD锚点完全相同，浏览器error日志为空。证据：[最终照片](screenshots/v3/final-resource-photo.png)、[返回状态JSON](source-evidence-v3/final-resource-return.json)。本轮既定功能检查已结束，未留下待执行的功能修复；旧lint基线及公开数据限制按上文保留。
