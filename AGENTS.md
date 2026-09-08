# HKUSTsandbox 工作约定

- 唯一工作根为 `/Users/herbit/Desktop/code/HKUSTsandbox`；仓库 `https://github.com/herbit2004/HKUSTsandbox`，默认分支 `main`。旧课程目录仅作兼容入口，禁止在那里维护另一份副本。
- 应用与完整素材只在 `versions/catalog.json` 的 latest 指定副本中维护。创建新节点用 `scripts/versions.py fork` 完整复制；旧副本禁止回写，各版素材不得软链接、硬链接或共用目录。每版保存自己的实体、楼层、Lift、来源和验收资料。
- 用户要求后续迭代持续提交/推送本仓库。每次只暂存本次审查过的项目文件，保留其他未提交工作；不要提交父仓库、凭据、node_modules、dist、.preview 或 .local。
- GOAL.md 是完整验收依据。G25 对所有具名实际物理楼要求照片/真实截图配对、可比 Academic 视角、Auto 与最高分别验收。迁移、构建或首帧可见不能将全校质量标为通过。
- 本机 full-local 资源与公开 government-baseline 包是两个有明确来源边界的数据配置。不要用公开底图覆盖本地完整数据。校方照片/平面/校徽与派生模型保持本地，未核实许可不得上传。
- 用户于 2026-09-08 明确要求 Sites 与本机完整效果一致，授权将 full-local 运行资源托管到仅所有者可访问的 `appgprj_6a9fc6574c708191822ce50bdf42d831`。这是上一条的私有 Sites 例外；完整资产仍不得进入 GitHub 公共仓库、Release 或公开访问的站点。继续部署前核实仅所有者访问。
- 固定预览为 http://127.0.0.1:4317/ 。检查现有监听与实际目录后操作；使用 scripts/preview-update.py 原子切换，并复用已有浏览器标签。
- 部分历史数据脚本需要已丢失的临时原始输入，见各版本的 docs/DATA.md。缺失时明确报出，不能用旧快照或生成假资料代替。
- 运行说明保存在 visual-quality-status.json 的 publishedRuntimeAcceptance。生成验收 Markdown 时必须保留该说明及原逐栋证据；不得删除历史服务名记录以绕过同步保护。

仅同步已有验收说明至 Markdown：`python3 scripts/versions.py exec python3 scripts/sync-building-quality-state.py --render-only`。不带该参数的完整清单同步仍保留防止删除历史身份的断言；不得绕过断言或删除原记录。
