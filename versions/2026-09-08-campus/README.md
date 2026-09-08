# Campus checkpoint · 2026-09-08

本目录是当前完整沙盘副本，包含自己的代码、运行模型与纹理、楼宇/室内信息、原始资料及验收证据。`VERSION.json` 区分项目节点日期和政府源日期；不将所有材料误称为2026年9月采集。

独立运行：

```sh
npm ci
npm run check
npm run build
python3 scripts/serve.py --port 4330
```

构建只读取本目录文件。根目录日常入口由 `versions/catalog.json` 的 latest 选择；创建副本、固定4317预览及Sites发布使用 [仓库根说明](../../README.md) 中的管理命令。部署工具统一从仓库根执行，不在单个版本里发布其他节点。

界面操作见 [使用说明](README.zh-CN.md)，完整验收依据见 [GOAL.md](GOAL.md)，素材来源与历史输入缺失见 [DATA.md](docs/DATA.md)。全校逐栋质量仍未完成，迁移和上线不改变这些状态。

GitHub仅保存可公开代码和说明，完整素材在本机副本及获授权的所有者私有Sites保存。本机 `INVENTORY.local.json` 可由根版本管理器核验。
