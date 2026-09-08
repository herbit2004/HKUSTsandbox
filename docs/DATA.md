# 版本数据

全部运行与原始素材已经迁入各自的 `versions/<id>/`，根目录不再放置 `public/` 或共享素材目录。完整数据约 1.8 GiB 运行资源，另有原始资料和本机证据。

当前详细来源、原始输入缺失说明和工具说明见 [当前版本 DATA.md](../versions/2026-09-08-campus/docs/DATA.md)。每次新建副本都复制其自己的资料说明；来源时间不随目录日期被改写。

公开下载的 `government-baseline-v1` 是一个约 107 MB 的简化可再分发包，不含全部实体、校方照片/平面/校徽或现状修补模型，也不是完整来源基线副本。下载工具与校验目录保存在每版的 `scripts/data-package.py` 和 `assets/government-baseline-v1.json`。只能安装进另行准备的空数据目录；工具拒绝覆盖已有完整数据。

完整副本的迁移应复制整个 `versions/<id>/`，随后运行 `python3 scripts/versions.py --version <id> verify` 核对其本机封存清单。不要只导出 public 就称为完整版本：楼宇研究、源材料、代码与证据也属于副本。

完整素材仅保留本机及用户授权的所有者私有 Sites；公共 GitHub/Release 的来源边界未改变。
