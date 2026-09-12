# Changelog

本文件记录尚未发布的本地开发版本；项目当前没有公开远程仓库或已发布包。

## Unreleased

- 只读 GitHub HTTP transport 的默认 User-Agent 与包版本统一为 0.2.0，并增加请求头契约断言，便于外部审计日志追踪实际工具版本。
- 缓存加载现在从同一次已校验读取判断 fresh/stale，避免并发原子替换时状态与返回载荷来自不同代文件。
- 进一步收紧 GitHub metadata/cache 路径：Windows junction/reparse point 和未折叠的 `..` 路径组件现在同样 fail-closed；cache 写入也能拒绝 dangling symlink 目标。
- 收紧 GitHub 元数据快照与缓存的路径边界：读取拒绝文件及已有父目录符号链接，缓存写入逐级安全创建普通目录；新增读写两侧路径重定向负例。
- 报告 JSON 与 SARIF 现在记录工具发行版本 0.2.0，与规则版本 0.2 分离，便于长期趋势和恢复工件追溯。
- baseline 比较在两份报告都声明工具版本且版本不一致时 fail-closed；旧版无工具字段的报告仍可与新版报告兼容比较。
- 同仓库 history JSON、趋势摘要和 Markdown 现在记录工具版本；旧版没有工具字段的历史仍可读取并继续追加。
- Runbook、Issue 和 CODEOWNERS 恢复草稿现在携带生成器版本，单独下载人工工件时也能追溯来源。
- 将包元数据与源码版本统一为 0.2.0，并增加一致性回归测试；报告规则版本仍独立保持为 0.2。
- Harden recovery artifact output: reject symlinked or non-directory path components before writing drafts.
- 恢复工件改为整套暂存后可回滚提交；中途替换失败会恢复旧一代，避免输出目录留下半套新旧混合草稿。
- 自带 continuity workflow 现在在 Ubuntu/Windows 矩阵上运行，使用对应 shell 写入 Job Summary，并分别上传完整报告与恢复工件。

- 报告现在包含可审计的 `privacy` 摘要：明确贡献者/CODEOWNERS 与仓库身份是否匿名化，并固定声明仓库内容上传为禁用；摘要不复制原始身份或路径。
- 报告写入层现在也拒绝 `upload_repository_content: true`，防止绕过 CLI 的调用产生自相矛盾的隐私证据。
- 报告与恢复工件共享匿名化快照校验；原始身份/路径不能伪装成已匿名化输出，失败时恢复目录也不会先创建。
- 恢复 Runbook、Issue、CODEOWNERS 草稿和 SARIF 现在同步携带非敏感隐私边界摘要，单独审阅恢复 artifact 时也能确认匿名化状态和仓库内容上传禁用。
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
- 独立社区场景文档增加 1 MiB 大小上限，并拒绝 declarative 场景中的 entrypoint，保持场景生态为 data-only、不可执行契约。
- builtin 场景入口现在必须匹配项目内三项已审阅的固定函数；未知入口直接拒绝，避免注册表演变成任意模块加载器。
- 场景与注册表加载器现在只接受普通文件并拒绝文件及父目录符号链接，避免贡献校验被重定向到未预期目标。
- 发布 wheel/sdist 验证器现在拒绝把产物与安装探针写入源码树内，保持“源码树外验证”契约。
- 发布验证输出目录现在拒绝文件及父目录符号链接，避免源码树外烟测被重定向到非预期位置。
- 标准库 GitHub transport 现在只投影分页/限流响应头，并将非 bytes 或不可读响应体转换为受控错误，避免凭证与远端诊断细节传播。
- CLI 原子输出现在拒绝文件及父目录符号链接，覆盖 collect-github、demo、history 和 baseline 工件，避免本地结果被重定向到未审阅目标。
- GitHub client 对响应 JSON 增加 64 层嵌套和循环结构边界，异常结构统一降级为 invalid_json。
- Composite Action 的 GITHUB_OUTPUT 现在同时拒绝文件和父目录符号链接，避免 runner 输出被重定向到未审阅位置。
- 场景注册表校验增加 64 层嵌套和循环结构边界，避免内存注入数据触发未处理递归异常。
- 增加根级可复用 Composite Action：安装动作自身并对 checkout 工作区运行本地演练；输入通过环境变量和 shell 数组传递，保留只读权限与 fork 边界。

## 发布说明

正式版本发布前应重新执行 [新颖性审计](docs/NOVELTY_AUDIT.md)、[发布清单](docs/RELEASE_CHECKLIST.md) 和跨平台 CI，并明确记录尚未验证的外部集成。
- 自带 `continuity.yml` 现在上传完整恢复目录（SARIF、Runbook、CODEOWNERS 草稿和 Issue 草稿），避免只保留机器可读结果而丢失人工审阅工件。
- 发布验证的 wheel/sdist 安装探针显式使用 `--no-build-isolation`，避免在离线或受限 runner 上为 sdist 隐式解析构建依赖。
- 恢复 Runbook、Issue 和 CODEOWNERS 草稿现在对仓库控制文本执行 Markdown 转义，并覆盖 `authorization:` 形式凭证脱敏，避免恢复工件被注入或泄露秘密。
