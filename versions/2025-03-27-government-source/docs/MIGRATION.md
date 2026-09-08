# 2026-09-08 独立仓库迁移

唯一后续工作根：`/Users/herbit/Desktop/code/HKUSTsandbox`。
公开仓库：<https://github.com/herbit2004/HKUSTsandbox>，默认分支 `main`。

源目录 `/Users/herbit/Documents/ChatGPT/ust选课/hkust-campus-3d` 属于没有提交历史的课程父仓库。独立仓库不继承父仓库 Git 元数据、课程文件或其他任务资料。

迁移先用 APFS copy-on-write 复制全部文件，再逐文件核对字节与软链接。原复制校验包含 150,231 个文件、46,573,732,706 字节；详细清单仅本机 `.local/migration/full-copy-verification.json` 保留。应用、模型、参考资料、未提交工作、依赖及所有历史预览快照均保留；缓存/快照不进入 Git。

验证新目录构建、服务与浏览器后，旧路径仅保留指向新根的兼容软链接，不保留第二份活工程。4317 必须由新根的 `scripts/serve.py` 运行，后续预览更新在新根执行。软链接只供旧书签/任务路径过渡，不能据其创建独立改动副本。

G25 全校统一证据标准与原验收结果完整保留。迁移完成只代表工程/运行/公开分发整理完成，不代表全校质量通过。验收 JSON 的 `publishedRuntimeAcceptance` 是运行注记的持久来源，Markdown 渲染会保留它；历史物理身份记录仍受禁止静默删除的保护。

公开 Git 仅跟踪项目代码、配置、精选文档和资产获取清单。校方照片/平面/派生外观及用户原始截图/逐字需求证据保留本机，不作未经许可的公开附件。公开政府数据 Release 不是本机 full-local 包。

仅同步已有验收说明至 Markdown：`python3 scripts/sync-building-quality-state.py --render-only`。不带该参数的完整清单同步仍保留防止删除历史身份的断言；不得绕过断言或删除原记录。
