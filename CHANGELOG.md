# Changelog

本文件记录尚未发布的本地开发版本；项目当前没有公开远程仓库或已发布包。

## Unreleased

- 增加确定性连续性模拟器、维护者/依赖/CI 三类核心演练。
- 三类核心演练统一输出事故积压、服务率与七天假设恢复窗口指标；恢复结果标明为模拟假设，不代表真实能力证明。
- 队列指标现在逐项进入结构化 Evidence，并在 Runbook 草稿中显示，避免恢复建议缺少可复核的模型输入与边界说明。
- 趋势历史新增不含本地路径的 history-summary.md，与 JSON 摘要一起原子写入，便于人工审阅同仓库分数变化。
- 场景生态新增只读 `describe-scenario PATH` 摘要命令，展示输入来源、恢复边界和限制但不暴露或执行 entrypoint。
- 为内置演练结果增加结构化证据链，并在报告中输出来源、字段与观测值。
- 基线比较拒绝跨 `rule_version` 报告，避免规则变化制造误导性回归结论。
- 新增只读 `validate-registry PATH` 命令，便于贡献者在提交前校验完整场景注册表。
- 报告新增不含原始记录的 `metadata_evidence`，明确 GitHub 观测的状态和评分边界。
- 增加版本化报告、稳定 Finding ID、基线回归门禁和本地趋势历史。
- 增加离线 GitHub 元数据快照、受控只读 GET transport 与默认禁用的 PR 评论草稿边界。
- 增加 10 个 data-only 社区场景样例和 3 个事故前/改进后 Demo。
- 增加 `maintainer-zero demo` 文本/JSON 输出、回归门禁，以及包内默认 Demo fixture。
- 加固 Demo 和场景输入校验：大小、字段、类型、计数、控制字符和禁止执行字段均有边界。
- 完成本地 wheel/sdist 构建和隔离安装烟测；CI 矩阵仍需由 GitHub Actions 实际运行确认。
- 增加 `collect-github OWNER/REPOSITORY` 显式只读采集命令；网络和环境 token 均需独立 opt-in，默认仍离线。
- 加固 GitHub 采集边界：仓库路径、分页/响应/总量上限、记录类型、有限超时和重定向行为均有测试。
- 增加显式 `--include-repository` 的有限仓库描述采集；快照和报告传播 `partial` 截断状态，避免把上限内计数误读为完整数据。
- 默认 starter 配置匿名化仓库名称/路径，并清理报告与本地 PR 草稿中的外部输入。
- 收紧 PR publisher 注入契约：校验幂等键和返回标识，隔离权限/远端异常且不自动重试。
- 增加带来源、TTL 和过期状态的本地 GitHub 元数据缓存契约；缓存默认离线、过期显式拒绝，且受大小/时间边界约束。
- 趋势 Markdown 摘要现在转义反引号、链接、强调、HTML、反斜杠和表格分隔符，并增加恶意场景名称负例，避免不可信历史字段改变文档结构。
- 在源码树外复验 wheel/sdist 双产物安装和内置 3 场景 demo；验证仍为本地离线流程，不代表已发布到 PyPI。
- 根目录 composite Action 改为通过有界环境变量适配器调用 CLI，暴露报告路径输出并支持本地元数据缓存输入；仍不联网、不写 GitHub。
- composite Action 增加 Windows `pwsh` 分支，与 Unix `bash` 分支保持同一输入/输出契约。
- composite Action 成功后同时暴露 JSON、Markdown、HTML 报告和恢复目录的绝对路径；失败门禁不会写入 `GITHUB_OUTPUT`。
- 增加根级可复用 Composite Action：安装动作自身并对 checkout 工作区运行本地演练；输入通过环境变量和 shell 数组传递，保留只读权限与 fork 边界。

## 发布说明

正式版本发布前应重新执行 [新颖性审计](docs/NOVELTY_AUDIT.md)、[发布清单](docs/RELEASE_CHECKLIST.md) 和跨平台 CI，并明确记录尚未验证的外部集成。
