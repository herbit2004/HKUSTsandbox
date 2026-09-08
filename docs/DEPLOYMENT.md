# 运行与部署

## 本地完整预览

在仓库根安装数据和依赖后执行：

```sh
npm run check
npm run build
python3 scripts/preview-update.py --existing-build
python3 scripts/serve.py --port 4317
```

`serve.py` 仅绑定 127.0.0.1，优先读取 `.preview/current`，不存在时读取 `dist/client`。原子发布后应核对首页哈希脚本和关键模型字节。`npm run dev` 与静态服务使用同一个端口，不能同时运行。

## 自托管静态站点

公开政府底图包可按其条款部署。完整本地包含未核实再分发许可的校方资产，部署前必须先取得相应权利；其本地保存不等于公开托管授权。

1. 按 README 安装数据，执行 `npm ci && npm run build`。
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

`npm run build:sites` 从当前仓库源码和校验过的 `government-baseline-v1` 构建纯静态 `out/`。所用临时目录在 `.local/`，构建后删除；不维护另一份工作副本，也不覆盖完整本地数据或 4317 快照。构建会验证所有 319 项资源的字节、SHA-256 和公开 profile，并拒绝夹带本地校徽、照片、校园图目录。

`.openai/hosting.json` 绑定本项目的唯一 Sites 项目，并选择 `out/`。在完成构建、提交当前源码并推送 Sites 源码仓库后，用 Sites 托管流程打包 `out/`、保存版本、部署并检查最终状态。源码也持续推送原 GitHub 仓库。凭据只用于单次命令授权，不进入文件、Git remote 或仓库配置。

初次部署保持仅所有者可访问。此版本没有 `/api/panorama`、校方室内资料或照片派生现状建筑；页面展示公开底图范围。不能把它描述为完整版上线或全校视觉质量验收完成。

截至 2026-09-08，[Sites 官方说明](https://learn.chatgpt.com/docs/sites) 公布每站 D1 10 GB、R2 无固定容量上限，但所有 Sites 合计仍受套餐限制；接近上限会提示，超限可能限制新建、增存储或高用量网站继续公开。公开文档未明确给出本账号的站点数、静态包、单文件、月流量、请求量和额度刷新周期，也未说明流量与模型额度的换算。当前静态部署未启用 D1 或 R2；一次包上传或部署成功不能证明其他容量和流量上限。

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

本说明的 Python/静态部署只提供 `dist/client` 文件，不运行 Node RSC 或开发服务器。不要把 `npm run dev` / Vite / Cloudflare dev 直接当生产公网服务；公开运行这些服务或处理不可信图像前需单独升级、审查适用告警并重验。

具体官方告警入口：[RSC](https://github.com/advisories/GHSA-wx67-qw84-cm4g)、[image-size](https://github.com/advisories/GHSA-w3rx-r6r6-pgpr)、[Vite](https://github.com/advisories/GHSA-fx2h-pf6j-xcff)、[Undici](https://github.com/advisories/GHSA-4cwx-7wf7-3272)、[Sharp](https://github.com/advisories/GHSA-f88m-g3jw-g9cj)、[ws](https://github.com/advisories/GHSA-96hv-2xvq-fx4p)、[esbuild](https://github.com/advisories/GHSA-g7r4-m6w7-qqqr)。这不是完整适用性安全审查；后续修复需与框架和数据工具兼容性一起验证。
