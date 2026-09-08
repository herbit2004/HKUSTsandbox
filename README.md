# HKUSTsandbox

HKUST 清水湾校区的 Three.js 交互沙盘。模型、地形、楼宇、楼层、房间、Lift 和参考资料属于同一个版本，地图是主要界面。

**全校逐栋视觉验收仍未完成。** 迁移、构建成功或上线不代表每栋已达到主学术大楼的标准。验收要求见 [GOAL.md](GOAL.md)，逐栋证据保存在各版本自己的 `docs/source-evidence-v4/building-quality/` 中。

## 版本目录

```text
HKUSTsandbox/
├── versions/
│   ├── catalog.json                  # latest 指向唯一构建和部署版本
│   ├── 2025-03-27-government-source/  # 原始政府摄影底图，配套资料注明整理日期
│   └── 2026-09-08-campus/             # 当前完整修补版
│       ├── VERSION.json              # 项目日期、来源日期、父版本与边界
│       ├── app/ components/ hooks/ lib/
│       ├── public/                   # 本版本全部运行资源与楼宇/室内信息
│       ├── source-geodata/            # 本版本政府源资料
│       ├── source-pathadvisor/        # 本版本校方地图/室内原始资料
│       ├── source-photo-references/   # 本版本参考照片
│       ├── docs/                     # 本版本设计、来源和验收证据
│       ├── scripts/ sites/ assets/    # 数据工具、Worker 和数据包目录
│       └── package.json + lockfile    # 可独立安装和构建
├── scripts/                          # 版本选择、快照、预览和发布管理
├── docs/                             # 仓库级版本与部署说明
├── .openai/hosting.json               # 唯一 Sites 项目配置
└── .local/ .preview/ out/             # 本机缓存、预览与发布产物，不入 Git
```

每份版本目录中的素材是独立普通文件，不链接到另一版本或共用素材目录。`2025-03-27` 是政府摄影底图的修订日期；不是这套应用、楼宇索引或所有照片的采集日期。历史底图节点的重建方式和资料时间边界见 [版本说明](docs/VERSIONS.md)。

GitHub 保存每版源码和可公开文档。完整素材已保存在本机对应目录，但受来源许可限制，不进入公共 GitHub 或 Release；拥有相应权限的完整版本可私下转移。代码 clone **不等于**下载了完整模型。

## 按需本机运行

日常查看使用 [线上 Site](https://hkust-sandbox.herbit2004.chatgpt.site/)。按用户要求，本地预览服务已停止，不默认常驻；以下命令仅用于临时开发验证，结束后关闭所启动的服务。

需要 Node.js ≥22.13、npm、Python ≥3.11，以及支持 WebGL 的浏览器。当前机器已经保留全部素材。

```sh
npm ci
npm run check
npm run build
python3 scripts/preview-update.py --existing-build
npm start
```

打开 <http://127.0.0.1:4317/>。根目录命令读取 `versions/catalog.json` 中的 `latest`，画布仍覆盖整页，侧栏悬浮于地图之上。`npm run dev` 与静态服务共用 4317 端口，二者不要同时运行。

若新版本修改了依赖锁文件，请在该版本目录重新执行 `npm ci`；发布工具会拒绝借用不匹配的根依赖缓存。

单独运行任一副本也可以：进入其目录，执行 `npm ci && npm run build`，然后 `python3 scripts/serve.py --port 4330`。它只读取自己目录中的素材。缺少完整数据的新 clone 请先阅读 [数据说明](docs/DATA.md)，不要用公开简化包覆盖完整版本。

## 创建下一个版本

先将当前节点验收、记录清楚，再创建完整副本：

```sh
python3 scripts/versions.py seal
python3 scripts/versions.py fork 2026-10-01-campus
```

`fork` 先验证父节点已有封存清单，再逐文件复制并校验 SHA-256，拒绝覆盖已有目录和素材链接；成功后才原子更新 `latest`。依赖安装、构建缓存和预览历史不属于素材，不复制进新版本。旧版本保留原文件。随后只修改新副本；构建、固定预览和 Sites 都自动跟随 `latest`。

```sh
python3 scripts/versions.py list
python3 scripts/versions.py --version 2026-09-08-campus verify
```

`verify` 将当前文件与该副本上次 `seal` 的完整本机清单比较。修改后的版本需完成适用验证再重新 `seal`；它是文件完整性检查，不是建筑视觉验收。

## 部署

私有站点：<https://hkust-sandbox.herbit2004.chatgpt.site>。只发布最新副本的运行内容，旧版本目录及原始资料档案不上站。

```sh
npm run build:sites
node --test scripts/sites-worker.test.mjs
```

完整运行文件位于 `out/runtime/`，小型 Sites Worker 部署包位于 `out/dist/`。模型、贴图和室内资源保持原始字节，使用 Sites R2 提供；不为上传限制降低画质。上传完成并核对全部对象后才切换线上资源清单。具体流程、全景代理和部署边界见 [部署说明](docs/DEPLOYMENT.md)。

工作根固定为 `/Users/herbit/Desktop/code/HKUSTsandbox`，默认分支 `main`。后续迭代提交/推送本仓库，但只暂存审查过的代码和可公开文档。见 [工作约定](AGENTS.md)、[第三方来源](THIRD_PARTY.md)、[政府源更新核查](docs/GOVERNMENT-SOURCE-UPDATE-20260908.md)。
