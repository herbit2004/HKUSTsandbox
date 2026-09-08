# 运行与部署

## 本地完整预览

在仓库根安装数据和依赖后执行：

```sh
npm run check
npm run build
python3 scripts/preview-update.py --existing-build
python3 scripts/serve.py --port 4317
```

`serve.py` 仅绑定 127.0.0.1，优先读取 `.preview/current`，不存在时读取 `versions/<latest>/dist/client`。原子发布后应核对首页哈希脚本和关键模型字节。`npm run dev` 与静态服务使用同一个端口，不能同时运行。

## 自托管静态站点

公开政府底图包可按其条款部署。完整本地包含未核实再分发许可的校方资产，部署前必须先取得相应权利；其本地保存不等于公开托管授权。

1. 进入选中副本目录，按其 README 准备数据，执行 `npm ci && npm run build`。以下静态服务命令都在该副本目录执行。
2. 将 `dist/client/` 的**内容**放到站点根目录，例如 `/srv/hkust/public/`。完整配置需要约 1.8 GiB 资产空间，另留解压、构建、前后两个快照空间；历史 38 GiB 快照无需部署。
3. 使用支持 `.glb`、JSON、JS 和纹理文件的静态服务器。下面是可直接调整域名/证书后的 Nginx server 片段：

```nginx
server {
    listen 80;
    server_name campus.example.org;
    root /srv/hkust/public;
    include mime.types;
    types { model/gltf-binary glb; model/gltf+json gltf; }
    location / { try_files $uri $uri/ =404; }
    location = /api/panorama { return 404; }
}
```

或者先用标准库进行服务器本机检查：

```sh
python3 -m http.server 8080 --bind 127.0.0.1 --directory dist/client
curl -I http://127.0.0.1:8080/
```

模型和 JSON 使用 `/models/...`、`/data/...` 等绝对 URL，**不支持未经改造的 `/HKUSTsandbox/` 子路径部署**。不要直接套 GitHub Project Pages 默认 URL。完整站点约 1.8 GiB，超过 GitHub Pages 1 GB 站点限制；GitHub 目前提供源码与可下载数据，Sites 部署见下节。

## ChatGPT Sites

当前站点 <https://hkust-sandbox.herbit2004.chatgpt.site> 仅所有者访问。用户已授权部署 full-local，与本机完整运行资源一致；不包含把完整素材上传公共 GitHub/Release 或开放公众访问。

`npm run build:sites` 只读取 `versions/catalog.json` 的 latest。它在一次性构建目录编译，逐文件比较原 public 与产物的 SHA-256，随后生成：

- `out/runtime/`：该版完整前端、模型、纹理、实体、室内资源与校验索引。
- `out/release.json`：原始 URL 到 SHA-256/大小/MIME 的映射，记录版本 ID。
- `out/dist/server/index.js`：Sites Worker，处理 R2 原始字节流、HEAD/Range/ETag 和 allowlist 全景代理。
- `out/dist/client/`：仅一个内部运行说明文件。Sites 优先服务匹配的静态文件，因此这里禁止放置 index、模型或 data，防止静态文件遮蔽 R2 的最新内容。

实际工具已确认：单次 Sites 部署归档上传上限 **512 MiB**；完整压缩包约 1.45 GB，不能直接上传。底层静态文件上限 **25 MiB**，而最大 iVillage GLB 为 57,847,228 bytes。因此资源使用 Sites R2，保持原始 GLB 和图片，不分辨率降级或重压模型。网站包本身只包含小型 Worker 和一个内部运行说明文件；R2 是必需绑定 `CAMPUS_ASSETS`，不需要 D1。

发布流程：

1. `npm run build:sites`；`node --test scripts/sites-worker.test.mjs`。
2. 核实 Sites 仍仅所有者访问。提交审查过的源码，推送 GitHub 和 Sites 源码仓库，读取推送成功后的完整 HEAD SHA。
3. 用 Sites hosting skill 的 `package-site.sh` 打包 `out/`。macOS 设置 `COPYFILE_DISABLE=1` 防止 AppleDouble 元数据。核对归档中是编译产物，不包含版本源目录、凭据或完整原始资料档案。
4. 在 Sites 环境中设置临时秘密 `HKUST_SITE_IMPORT_TOKEN`，保存该源码 SHA 的版本并私有部署，等待成功。
5. 将既有 Sites 访问凭据置于进程环境 `HKUST_SITES_CHECK_TOKEN`，临时导入秘密置于 `HKUST_SITE_IMPORT_TOKEN`，执行 `node scripts/import-sites-runtime.mjs https://hkust-sandbox.herbit2004.chatgpt.site`。凭据不得写进文件、Git 配置、日志或命令示例。
6. 导入器分批检查资源，流式上传缺失对象，由 R2 校验 SHA-256；全部对象大小和存在性通过后，才原子切换 active 清单。只上传最新运行资源，不上传其他版本、source-* 或历史 QA 档案。
7. `node scripts/verify-sites-runtime.mjs https://hkust-sandbox.herbit2004.chatgpt.site` 核对完整 profile、校验索引、主要模型/贴图/室内/资料和全景。完成真实浏览器检查。
8. 移除临时导入环境秘密，并重新部署同一保存版本以应用环境变更。未配置秘密时导入端点返回 404。保留现有访问设置与 R2 数据。

部署回执和完整核查清单位于 `.local/sites-*.json`，不包含凭据，不作为全校逐栋视觉验收通过的证据。运行素材保留原 URL，允许原来的按区域有界懒加载；上站不会补足本来尚未完成的建筑质量工作。

[官方 Sites 说明](https://learn.chatgpt.com/docs/sites) 说明 R2 没有单站固定容量上限，但所有 Sites 合计仍受套餐限制；实际额度和流量限制不能从一次部署成功推断。[Cloudflare Workers 限制](https://developers.cloudflare.com/workers/platform/limits/) 与 [R2 API](https://developers.cloudflare.com/r2/api/workers/workers-api-reference/) 说明底层文件、请求与流式对象接口。这里不承诺无限容量或无限流量。

## 按需全景

纯静态服务不能实现 `/api/panorama`。公开 baseline 没有全景功能。完整本地 `serve.py` / Vite 服务提供限定已知公开节点 ID 的代理；离线时模型仍可运行，全景请求可能失败。需要全景的自托管环境可在 Nginx 的 `/api/panorama` 位置反代到同机、仅 loopback 监听的 `serve.py`，其他路径仍使用静态文件。该代理最长等待 40 秒、最大图片 32 MiB，应配置相应超时，勿任意放宽 URL allowlist。

Release 是安装包下载渠道，不是模型 CDN；安装脚本下载并核验后，在同一站点本地提供模型。

## 本次安装发现的依赖告警

2026-09-08 07:22 UTC 的干净 `npm ci` 官方响应报告 11 个受影响包：8 high、2 moderate、1 low；迁移保留原锁文件，未将其判为安全通过。主要包括直接 RSC 依赖、vinext 的 image-size，以及 Vite、Undici、Sharp、ws 和 esbuild 工具链。

| 受影响包/链路 | 依赖位置与实际边界 |
|---|---|
| `react-server-dom-webpack` | 直接生产依赖，供 RSC 框架路径使用；当前 Python/纯静态站点不运行 Node RSC 请求处理。 |
| `image-size` ← `vinext` | 生产依赖链中的图像解析工具；不运行于本次 Python 静态文件服务。处理不可信图像或启用框架服务前仍需评估。 |
| `vite` ← `vinext` peer / 开发命令 | 构建和开发服务器使用；lock 中的 production 标记不代表静态浏览器会执行其 Node 服务端。 |
| `undici`、`sharp`、`ws`、`esbuild` ← Miniflare/Cloudflare/shadcn 等 | 主要为构建、开发和可选数据/QA工具的传递依赖；不由当前静态 HTTP 请求路径调用。 |
| `vinext`、`miniflare`、`@cloudflare/vite-plugin`、`wrangler` | 汇总中包含从上述依赖继承的告警，不能将11个受影响包计作11项独立、已证实可远程利用的问题。 |

实际适用性取决于启用的服务、输入和部署方式；本次没有完成全面安全审查。公开数据安装工具使用 Python 标准库下载、校验并限制解包路径；本次核对没有发现它调用上述受影响 Node 包。

本说明的 Python/静态部署只提供 `versions/<latest>/dist/client` 文件，不运行 Node RSC 或开发服务器。不要把 `npm run dev` / Vite / Cloudflare dev 直接当生产公网服务；公开运行这些服务或处理不可信图像前需单独升级、审查适用告警并重验。

具体官方告警入口：[RSC](https://github.com/advisories/GHSA-wx67-qw84-cm4g)、[image-size](https://github.com/advisories/GHSA-w3rx-r6r6-pgpr)、[Vite](https://github.com/advisories/GHSA-fx2h-pf6j-xcff)、[Undici](https://github.com/advisories/GHSA-4cwx-7wf7-3272)、[Sharp](https://github.com/advisories/GHSA-f88m-g3jw-g9cj)、[ws](https://github.com/advisories/GHSA-96hv-2xvq-fx4p)、[esbuild](https://github.com/advisories/GHSA-g7r4-m6w7-qqqr)。这不是完整适用性安全审查；后续修复需与框架和数据工具兼容性一起验证。
