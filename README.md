# HKUSTsandbox

香港科技大学清水湾校园的 Three.js 交互沙盘：地形、摄影网格、建筑实体、原位楼层与地图浏览。An independent workspace for the HKUST Clear Water Bay campus sandbox.

**全校逐栋视觉验收仍未完成。** 初始画面、构建成功或加载计数不代表每栋已达到主学术大楼标准。统一要求见 [GOAL.md](GOAL.md)，状态见 [逐栋验收表](docs/source-evidence-v4/building-quality/visual-quality-status.md)。

## 先选择数据范围

| 数据 | 获取方式 | 包含与限制 |
|---|---|---|
| 公开政府底图 `government-baseline-v1` | 下述带 SHA-256 校验的 Release 下载命令 | 292 个真实摄影瓦片及政府地形。保留源时代外观；不含校方平面、校徽、照片、现状重建楼或全量实体功能，不能当作完整现状校园。 |
| 完整本地数据 `full-local` | 本机已迁移保留；其他机器需拥有相应权利的本地导出包 | 约 1.8 GiB 运行资源，含现有实体、楼层、细节模型及参考资料。用户已授权用于仅所有者访问的 Sites；不上传 GitHub 公共仓库或 Release。 |

代码 clone 不自带全部大模型。公开包下载后可离线运行基础三维地图；完整本地资料不降级为公开底图。详见 [数据准备与来源](docs/DATA.md)、[第三方权利边界](THIRD_PARTY.md)。

## 安装与运行

需要 Node.js **22.13 或更高版本**、npm、Python **3.9+**；浏览器需支持 WebGL。迁移验证使用 Node 25.8.1 / npm 11.11.0 / Python 3.9。

```sh
git clone https://github.com/herbit2004/HKUSTsandbox.git
cd HKUSTsandbox
python3 scripts/data-package.py fetch
npm ci
npm run check
npm run build
python3 scripts/preview-update.py --existing-build
python3 scripts/serve.py --port 4317
```

打开 <http://127.0.0.1:4317/>。数据已在本机时跳过 `fetch`；它拒绝覆盖已有运行数据。`npm run dev` 在相同 4317 端口启动开发服务器，与静态预览二选一，避免同时占用端口。数据 profile 与部分空间描述在构建时载入，换数据包后必须重新构建。

现有完整版工作副本的唯一根目录：`/Users/herbit/Desktop/code/HKUSTsandbox`。双击 `启动校园地图.command` 可运行已构建版本。左键旋转、右键锚定平移、滚轮缩放；详细使用与现有模型边界见 [完整本地使用说明](README.zh-CN.md)。

## 目录

```text
app/ components/ hooks/ lib/  应用、场景、交互与界面
scripts/                     构建、数据处理、受控验证与运维
assets/                      公开数据版本、下载地址、大小和校验和
public/                      已安装运行资产；仅少量自编工具入 Git
source-geodata/              本地政府源资料及处理工具
source-pathadvisor/          本地校方原始资料及处理工具
source-photo-references/     本地参考照片；不公开再分发
docs/                        设计、来源、QA；大部分证据附件仅本地
.local/                      迁移校验、缓存、日志、数据导入/导出
dist/ .preview/ node_modules/ 本地产物、历史快照与依赖；不入 Git
```

未重新组织已有模型 URL 和证据目录，避免破坏实体关系。历史截图与逐字需求附件本地保留，公开文档中的这些链接不表示附件也随 clone 发布。

## 构建、部署与更新

默认支持**域名根路径**静态部署，完整本地服务还提供按需官方全景代理。可执行命令、Nginx 示例、资源需求与数据权利边界见 [部署说明](docs/DEPLOYMENT.md)。本项目没有自动部署 GitHub Pages，也不把 Release 下载地址当浏览器 CDN。

Sites 的完整私有版本使用 `npm run build:sites`，读取本机 `full-local`，保持模型、纹理和室内资源的原始字节，支持全景代理。仅拥有公开数据时使用 `npm run build:sites -- --profile government-baseline`。二者在临时目录构建到 `out/`，均不替换本机 `public/`、`dist/` 或固定 4317 预览。站点为 <https://hkust-sandbox.herbit2004.chatgpt.site>，完整资源只允许所有者访问；配置在 `.openai/hosting.json`，打包与验证见 [部署说明](docs/DEPLOYMENT.md)。

后续所有修改在本仓库完成：修改 → 适用检查 → 构建 → `python3 scripts/preview-update.py --existing-build` 原子切换固定预览 → 实际检查 → Git 提交/推送。不要再在旧课程目录维护第二份工程。具体要求见 [AGENTS.md](AGENTS.md) 和 [迁移说明](docs/MIGRATION.md)。

```sh
git status --short
git add <本次已审查的文件>
git commit -m "Describe the change"
git push origin main
```

公开资产更新先检查来源许可，再创建新的不可变数据版本、校验文件和 Release。不要将完整本地校方照片/模型包或历史快照加入 Git。

## 来源与许可

公开底图使用香港特别行政区政府地政总署的 3D Visualisation Map、土木工程拓展署 LiDAR DTM（相关处理范围和日期随包记录）。政府数据依 [CSDI 使用条款](https://portal.csdi.gov.hk/csdi-webpage/doc/TNC) 提供，保留政府与来源署名。数据修订日期不是拍摄日期。

项目代码未新增统一开源许可证；第三方代码遵循各自许可证，第三方数据、校方照片/平面/校徽不因仓库公开获得额外授权。详情见 [THIRD_PARTY.md](THIRD_PARTY.md)。
