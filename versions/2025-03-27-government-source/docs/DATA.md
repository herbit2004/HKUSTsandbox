# 数据准备与可复现范围

## 公开政府底图

`python3 scripts/data-package.py fetch` 从本仓库不可变 Release 下载 `government-baseline-v1`。`assets/government-baseline-v1.json` 记录准确压缩大小、SHA-256、解包文件与来源，工具在写入前校验。可先下载到离线机器，再运行 `python3 scripts/data-package.py install /path/to/government-baseline-v1.zip`。

包包含现有 292 个政府摄影预览 GLB、DTM 地形与必需的空可选功能描述；它是实际地理数据子集，不是合成演示，也不是当前已建成校园的完整表达。校方楼层、实景照片、校徽、照片派生重建外观、详细实体注册表不在此包。页面会标示该范围，关闭不可用的校方图像入口。公开包 profile 在构建时固定；换数据后重新构建。

## 完整本地包

已迁移工作根保留全部 `public`、`source-*`、历史证据和快照。正常运行无需再下载来源；`public` 约 1.8 GiB。授权持有者可离线转移自己的运行资源：

```sh
python3 scripts/data-package.py export-local /path/to/full-local-data.zip
# 在另一份干净 clone 中：
python3 scripts/data-package.py install /path/to/full-local-data.zip
npm ci
npm run check
npm run build
```

导出包含逐文件校验，**不得将 full-local 包上传本 public 仓库或 Release**。工具默认拒绝覆盖已安装数据；切换数据前保留自己的包，在独立 clone 中测试最安全。原始资料/证据不属于运行包，仍在本机 `source-*` / `docs`；迁移校验清单在 `.local/migration/`。

## 取得源资料

- [CSDI 3D Visualisation Map](https://portal.csdi.gov.hk/csdi-webpage/metadata/landsd_rcd_1671677054006_62261/html)、[CEDD LiDAR](https://portal.csdi.gov.hk/csdi-webpage/metadata/cedd_rcd_1629267205233_87895/html)：官方开放入口、坐标及处理说明见 `source-geodata/README.zh.md`。公开包保留了转换后的本项目子集，不要求先下载全港数据。
- [HKUST Path Advisor](https://navigate.ust.hk/path/app/)：公开楼层入口与自编下载脚本保留于 `source-pathadvisor/`。需要重新获取时按该目录说明运行 `download_floors.py` 等脚本；公开可访问不等于允许重新分发其完整资料。
- [HKUST 校园地图](https://mtpc.hkust.edu.hk/resources/campus-location-maps)：获取平面图的官方入口。照片逐项来源保存在本地原始 manifest，公开仓库不复制照片、全景与校徽。

## 数据生成链的真实限制

现有链路包括政府源下载/转换 → preview/terrain；PathAdvisor 下载 → 楼层/实体；原生细节及现状模型 → 纹理/遮罩 → 验收。已有转换与审计脚本都保留，但不存在一个可证明重放全部历史产物的一键 pipeline。

迁移时核实，代码引用的 35 个 `/tmp/hkust-*` 历史输入/阶段目录全部已不存在，包括 iVillage terminal triangles/roof-grid、部分高层原始源、Hall 照片阶段和历史射线输入。源项目内的现有文件全部迁移，缺失的临时输入不能从文件名重新构造。可重新取得的原始数据需从上列官方入口取得并核对日期/校验；不能声称所有 current-form 外观可以在干净 clone 端到端再生。

这些历史脚本不是运行地图的必要步骤。调用前查看脚本的 `--source`、`--stage`、`--output` 参数和输入文件要求；将重新取得的工作数据放入 `.local/cache/` 并显式传参。无参数且仍使用历史 `/tmp` 输入的审计工具，需要明确重新配置后才能运行。

Python 预览服务仅依赖标准库。可选数据处理依赖列表在 `requirements-data.txt`；涉及 GDAL/rasterio、Blender 或特定历史源的脚本还有各自环境要求，未将可选工具当作运行前置条件。
