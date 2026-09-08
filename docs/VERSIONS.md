# 完整版本管理

`versions/catalog.json` 是唯一版本选择入口。`latest` 同时用于根目录的 check/build/dev、固定 4317 预览构建和 Sites 构建；部署输出不遍历其他版本。

每份副本包含自己的应用源码、依赖锁文件、运行模型与纹理、地形、楼宇实体、楼层/房间/Lift 信息、原始来源和研究/验收附件。素材使用普通文件复制，不通过软链接、硬链接或公共素材池关联其他副本。操作系统缓存、node_modules、dist、.preview 和 .local 可重建，不属于版本素材。全校逐栋质量仍按副本内 GOAL.md 和证据表验收。

## 现有节点

- `2025-03-27-government-source`：由保留的政府原始摄影网格整理的来源基线。日期对应 tile-based 数据修订。配套应用代码、实体/楼层索引和补充资料在 2026-09 整理，标注为后加注释；不声称保存了一个当时并不存在的 2025 应用或现场状态。当前修补模型不作为这个节点的原始底图使用。
- `2026-09-08-campus`：迁移时完整本机修补节点，包括 iVillage 与李家誠創科大樓派生模型及纹理、全部现有实体和证据。不同源的日期保持原记录，没有把它们统一伪称为 2026-09 拍摄。

历史源脚本引用的部分 `/tmp/hkust-*` 输入早已丢失；本次保留现存输入和完成产物，并未补造缺失历史。详见各副本 `docs/DATA.md`。来源基线是有边界的可复现整理，不能冒充最早下载当天的完整机器快照。

## 操作

```sh
python3 scripts/versions.py list
python3 scripts/versions.py seal
python3 scripts/versions.py fork YYYY-MM-DD-campus
python3 scripts/versions.py --version YYYY-MM-DD-campus verify
python3 scripts/versions.py exec python3 scripts/sync-building-quality-state.py --render-only
```

`fork` 先核对父节点已有封存清单（未封存的初次节点先建立清单），再逐文件复制并核验，最后更改 latest。复制失败不会切换 latest，也不会覆盖任何历史副本。`INVENTORY.local.json` 是包含完整私有文件 SHA-256 的本机清单，不上传 GitHub。新副本进入编辑后，旧节点不再回写；archived 节点拒绝重写封存清单。父节点若已有未记录的改动，fork 会停止，不会默默认可这些改动。

按需官方全景仍依赖远端服务。本机已下载图片和完整节点索引各自保存在副本中；未下载的网络内容不属于已封存材料，不声称它们已离线归档。

发布只选择 latest 的 `public/` 和前端/Worker 编译结果；`source-*`、历史截图、其他版本及本机预览历史不会成为部署素材。线上 R2 中使用 SHA-256 地址与原始 URL 的映射保证逐文件字节一致；这是发布传输格式，仓库各副本仍独立保存自己的物理文件。

公共 GitHub 只含代码、版本元数据和许可允许的文档。因此公共 clone 缺少私有完整素材时，应明确报缺失，不能把公开简化政府包伪称为对应的完整副本。
