# 长期目标：将 Maintainer-Zero 做成可信、可复用的开源连续性演练工具

## 总目标

把 `D:\maintainer-zero` 从本地启发式 MVP 推进到可用于真实 GitHub 仓库的连续性灾难演练平台。每个阶段必须交付可运行代码、自动化测试、可解释报告、明确的隐私边界和文档，并在本地 Git 中形成独立提交。

最终用户应能在 5 分钟内完成一次演练，回答：核心维护者、关键依赖或 CI/发布链路失效后，哪些能力会中断、多久开始积压、有哪些可验证的恢复路径、应先补齐哪些责任与文档。

当前增量：模拟输出附带 `artifact-manifest.json`，可用 `verify-manifest` 在本地离线校验大小与 SHA-256。它不包含自身 hash，不是数字签名，也不证明来源可信。
GitHub composite Action 也暴露该 manifest 的绝对路径并将其纳入连续性 workflow artifact；Action 仍只做本地分析，不上传源码或执行 GitHub 写操作。

## 完成定义

1. 所有结论带有输入证据、规则版本、假设和置信度；不把缺失数据当作安全。
2. 同一快照与参数重复运行结果一致，支持基线和改进方案的反事实比较。
3. 支持本地 Git 与可选 GitHub 只读元数据采集。
4. 三个核心场景有真实事件时间线、积压与恢复指标，并有负例测试。
5. CLI、JSON/Markdown/HTML 报告、CI 评分门禁、恢复工件草稿可直接使用。
6. 私密数据默认留在本地；匿名化、输出转义、超时、大小限制和最小权限有测试。
7. 通过跨平台测试、打包安装测试、样例仓库端到端测试和发布前对抗审查。

## 分阶段执行

### M1 — 可信的本地基础（立即执行）

- [x] CLI 读取并验证 `continuity.json`，命令行参数优先。
- [x] 拒绝非 Git 目录，避免静默输出误导性分数。
- [x] 作者与 CODEOWNERS 匿名化选项生效。
- [x] 短演练时间线不越界，无依赖时使用不适用语义。
- [x] `--fail-under` 返回明确退出码：0 成功、1 门禁失败、2 输入错误。
- [x] 维护者离开场景接入确定性积压模拟器。
- [x] 消除核心场景的时间线越界与无依赖误报歧义，并暴露确定性积压指标。
- [x] 补齐采集、配置、报告、CLI 和隐私端到端负例测试。

### M2 — 基线比较与恢复工件

- [x] 新增版本化报告 schema、稳定 finding ID 和规则版本。
- [x] 支持 `--baseline` 比较分数、场景、风险和数据覆盖变化。
- [x] 支持显式选择分数下降门禁和新增高危风险门禁策略。
- [x] 生成 Runbook、CODEOWNERS、Issue 草稿，不自动写入外部系统。
- [x] 输出 SARIF、PR 摘要和可离线打开的友好报告。

### M3 — GitHub 元数据与可复用集成

- [x] 建立注入式只读元数据客户端边界，支持白名单路径、分页、超时参数、大小上限和权限/传输降级；CLI 通过显式 `collect-github` 接入；reviews 仅在显式指定单个 PR 时采集。
- [x] 离线快照保留观测事实与 unknown 状态，并可通过 CLI 注入报告；标准库 HTTP GET transport 已完成，支持显式仓库描述采集并将分页截断标记为 `partial`，速率等待和缓存仍由调用方负责。
- [x] 当前 CI/演练工作流使用最小 `contents: read` 权限，不使用 `pull_request_target` 或外部写权限；根目录提供可审阅的本地 composite Action 契约，Marketplace 发布仍待完成。
- [x] PR 评论默认只生成本地草稿；显式注入 publisher 后使用稳定幂等键，真实 GitHub 写入仍由集成方负责。
- [x] 保留本地报告历史与同仓库趋势，不进行跨项目误导性排名。

### M4 — 场景生态与发布准备

- [x] 发布第一版版本化事故场景格式与贡献校验器；内置注册表覆盖 3 个核心场景。
- [x] 扩展到 10 个可复用、数据-only 样例，并为每个样例声明阻塞恢复边界。
- [x] 提供 3 个“事故前/改进后”可复现、数据-only demo。
- [x] 独立核验相邻项目，更新新颖性边界，不宣称绝对无人做过。
- [x] 完成本地发布前安全审查、文档验证、wheel/sdist 安装烟测和离线真实 Git 仓库端到端 fixture；CI 矩阵仍由工作流执行。
- [x] 整理英文 README、中文指南和变更日志；正式发布资产仍需用户授权后生成或发布。

## 执行规则

- 一次推进一个可以验收的增量，先修复影响结论可信度的问题，再扩展传播功能。
- 多 agent 只承担边界明确的模块；共享文件由主代理整合，避免并发覆盖。
- 每轮记录：完成内容、验证结果、剩余风险、下一项。
- 本地实现与测试可自主推进；创建公开远程仓库、push、发布包、发布报告、花费或修改真实项目权限，必须另获用户授权。
- 遇到技术失败先排查与降级；只有需要新增权限或外部决策时才停下询问。

### 离线端到端证据

tests/test_e2e_fixture.py 使用真实 Git 历史的最小仓库 fixture，验证本地分析、三类演练、脱敏报告、恢复工件、基线比较以及依赖膨胀后的回归门禁。该测试不联网、不读取 token，所有输出仅写入临时目录；详见 E2E_FIXTURE.md。

## 当前执行记录

- 2026-09-12：为隐私保护公开基准增加独立 `validate-benchmark PATH` 只读入口。导出摘要现在可在分享前通过严格 schema、隐私声明、资源分区、确定性排序和总分一致性校验；加载器限制普通文件、大小、重复 JSON 键、非标准数值及读取竞态，不联网、不执行代码，也不形成跨项目排名。

- 2026-09-12：GitHub 只读采集结果显式标记 \`provider: github\`，将真实采集器接入 provider-neutral 快照协议；未声明 provider 的旧快照继续兼容，未引入 GitLab/Forgejo 网络或认证能力。
- 2026-09-12：统一 metadata cache 与快照的 JSON 歧义边界：缓存读取拒绝重复 key 和非标准数值，新增离线负例；provider-neutral 快照契约仍保持同一缓存/权限/隐私语义。
- 2026-09-12：新增 provider-neutral 离线元数据快照协议：可选 github/gitlab/forgejo provider 共用规范化资源、权限、unknown/partial 和隐私投影；新增 validate-metadata 命令。此阶段不提供 GitLab/Forgejo 网络客户端，避免把协议支持误报为已完成平台集成。
- 2026-09-12：新增离线 `normalize_metadata()` canonical mapping 契约，覆盖 GitLab project/merge request 与 Forgejo/GitHub 常用别名；未知键、别名冲突、嵌套值和身份/凭证字段均 fail-closed。该增量仍不提供 GitLab/Forgejo 网络客户端。
- 2026-09-12：新增注入式 GitLab/Forgejo 只读 provider client：固定 API 路径、数字 project id/OWNER-REPOSITORY 标识、分页/响应/超时上限和有界限流提示；所有记录先做字段投影再 canonical 校验。GitLab reviews 仍保持 unknown，客户端不读取 token、不自动重试、不执行或写入远端。
- 2026-09-12：加固 provider adapter 的数值边界：canonical 标量拒绝超出 64 位的整数，限流头先做长度检查再转换；新增超大整数与恶意超长 header 负例。
- 2026-09-12：新增 GitLab/Forgejo 显式 opt-in HTTPS GET transport：固定 provider 路径、HTTPS-only、禁止重定向、响应/超时/响应头边界和环境 token opt-in；fake opener 回归不连接真实平台。
- 2026-09-13：新增 collect-provider CLI，将 GitLab/Forgejo 的注入式客户端与 HTTPS transport 接入可直接运行的命令；网络、HTTPS API base、分页/超时/响应大小和环境 token 均显式 opt-in，输出与 cache 复用原子写入和同一 canonical 校验。真实 provider 访问仍需用户授权，GitLab reviews 保持 unknown。
- 2026-09-13：修正 provider 分页参数差异：GitLab 使用 per_page，Forgejo 使用 limit，并新增契约测试；避免服务端忽略未知参数后让页大小与 partial 语义失真。
- 2026-09-13：collect-provider 在构造 transport 前校验 cache TTL（1 至 30 天），非法缓存配置不会触发网络请求或留下半套快照。
- 2026-09-12：基线比较新增结果分数 schema 校验与有限数值边界，非法超大整数、NaN/Infinity 及原始范围外小数在读取阶段拒绝；新增 4 项负例并通过专项测试。
- 2026-09-12：benchmark 导出与 baseline 报告读取新增歧义输入防护：重复 JSON key、非标准数值（NaN/Infinity）和超大整数均 fail-closed；分数先验证原始范围再做确定性舍入，独立文本渲染也校验场景/置信度及 Unicode 控制字符。专项与全量回归通过。
- 2026-09-12：补齐 composite Action 输出边界的 reparse point 模拟测试，覆盖 `GITHUB_OUTPUT` 父目录与最终文件；路径校验现在有 Unix 符号链接、硬链接和 Windows reparse 负例证据。
- 2026-09-12：报告输出从逐文件原子替换提升为整套可回滚替换；模拟中途替换失败时，旧的 JSON/Markdown/HTML 组合保持不变，新增三文件回滚负例。
- 2026-09-12：报告三文件输出新增整套目标预检；任一 `continuity.json`、`report.md` 或 `report.html` 目标冲突时，在首次替换前 fail-closed，新增半套报告防护负例。
- 2026-09-12：补齐社区场景加载器的跨平台路径边界：注册表与 data-only 场景文件逐级拒绝 POSIX 符号链接、Windows junction/reparse point 和特殊文件，新增 reparse 模拟负例。
- 2026-09-12：恢复工件原子替换新增整套目标预检；若 Runbook、CODEOWNERS、Issue 或 SARIF 任一目标是符号链接、reparse point 或特殊文件，写入会在首次替换前 fail-closed，避免留下半套恢复证据；新增回归负例。
- 2026-09-12：补齐报告与 history 输出路径边界：报告原子写入和趋势历史现在逐级拒绝父目录符号链接、Windows reparse point、特殊文件及超大 history，新增输出重定向负例。
- 2026-09-12：统一只读 GitHub transport 的默认 User-Agent 与包版本 0.2.0，并补充请求头追踪测试；日志中的客户端版本不再停留在 0.1。
- 2026-09-12：修复 metadata cache 的双重读取竞态：fresh/stale 判断与返回载荷现在来自同一次校验读取，新增替换期间一致性负例。
- 2026-09-12：补齐 metadata/cache 的跨平台路径边界：保留 `..` 组件逐级检查，拒绝 Windows junction/reparse point，并在 cache 原子替换前检查 dangling symlink 目标；新增跨平台路径负例。
- 2026-09-12：收紧 GitHub metadata/cache 的目录路径边界：快照读取、缓存读取和缓存原子写入现在逐级拒绝已有父目录符号链接；缺失缓存目录仅按普通目录逐级创建，新增读写两侧重定向负例。
- 2026-09-12：统一三类核心场景的确定性队列证据：维护者离开、依赖撤包和 CI 中断现在都输出事故窗口内峰值/结束积压、服务率，以及事故结束后七天的假设恢复窗口；恢复容量和恢复日明确标记为模拟假设，不会被解释为真实可用性证明。
- 2026-09-12：将三类场景的队列聚合指标逐项写入结构化 Evidence，并同步到恢复 Runbook 草稿；恢复工件明确区分模型结果与真实恢复证明。
- 2026-09-12：为同仓库历史增加不含本地路径的 Markdown 趋势摘要；JSON 与 Markdown 均通过同目录原子替换生成，unknown 保持为不可观测而非零风险。
- 2026-09-12：为社区场景增加只读 `describe-scenario PATH` 契约摘要，统一展示输入来源、恢复动作、限制和执行模式；摘要不会执行 entrypoint 或公式。
- 2026-09-12：扩展 composite Action 输出契约，成功运行时同时暴露报告目录、JSON/Markdown/HTML 报告和恢复工件目录的绝对路径；门禁失败或输出边界失败均不写入 `GITHUB_OUTPUT`，并补齐 Unix/Windows 共用适配器测试。
- 2026-09-12：将隐私配置提升为报告中的可审计摘要；JSON、Markdown 和 HTML 现在明确记录身份/仓库匿名化状态与仓库内容上传禁用状态，同时不复制原始姓名、owner 或本地路径；补充直接报告与真实 Git fixture 回归测试。
- 2026-09-12：报告和恢复 API 共享 fail-closed 的快照投影校验；匿名化声明与原始身份/路径不一致时拒绝输出，避免绕过 CLI 产生虚假隐私证据。
- 2026-09-12：恢复 Runbook、Issue、CODEOWNERS 草稿和 SARIF 同步输出非敏感隐私边界摘要；单独下载恢复 artifact 时仍可审计匿名化状态与仓库内容上传禁用。
- 2026-09-12：将 Python 包版本统一为 0.2.0，并用自动化测试校验 pyproject.toml 与包内 __version__ 一致；报告规则版本 0.2 继续作为独立协议版本。
- 2026-09-12：报告 JSON 与 SARIF 增加工具发行版本证据，并与规则版本分离；新增报告和恢复工件回归测试，避免长期趋势无法区分工具实现变化。
- 2026-09-12：基线比较增加工具版本边界：两份报告均声明且不一致时拒绝比较，旧版缺少工具字段时保留兼容读取；新增跨工具版本负例。
- 2026-09-12：同仓库历史 JSON 与趋势 Markdown 增加工具版本字段；旧版历史继续兼容读取，跨工具版本追加会 fail-closed，避免长期趋势混入不同实现。
- 2026-09-12：Runbook、Issue 与 CODEOWNERS 恢复草稿增加生成器版本标识，并补充单独下载工件的追溯测试。
- 2026-09-12：恢复目录改为整套工件暂存、原子替换并支持中途失败回滚；新增回归测试证明既有 Runbook、CODEOWNERS、Issue 和 SARIF 不会被半套更新覆盖。
- 2026-09-12：自带 continuity workflow 扩展为 Ubuntu/Windows 矩阵，分别使用 bash/PowerShell 发布 Job Summary，并为每个 runner 上传完整且独立命名的报告与恢复工件；本地契约测试覆盖工作流结构，真实远程 runner 仍需实际执行确认。
- 2026-09-12：连续性 workflow 的摘要与 artifact 发布改为 `always()`；分数或基线门禁失败时仍保留可审阅报告，初始化失败时使用 warning 避免 artifact 步骤掩盖原始错误；补充工作流契约断言。
- 2026-09-12：社区场景独立 JSON 增加 1 MiB 大小上限；data-only declarative 场景若声明 entrypoint 直接拒绝，确保场景注册表不会演变成任意代码执行入口；新增安全负例。
- 2026-09-12：builtin 场景入口收紧为项目内三项已审阅固定函数，未知入口 fail-closed；补充注册表安全负例，避免未来执行器把外部字符串当成任意模块加载目标。
- 2026-09-12：场景与注册表读取增加普通文件及全路径符号链接边界，并用已打开描述符复核目标一致性；新增路径安全负例。
- 2026-09-12：发布验证器拒绝源码树内的输出目录，确保 wheel/sdist 安装烟测不会污染 checkout；新增路径边界负例，并在 D:/Codex 完成双产物验证。
- 2026-09-12：发布验证器进一步拒绝输出路径中的文件及父目录符号链接，避免源码树外烟测被重定向；新增符号链接负例。
- 2026-09-12：标准库只读 GitHub transport 收紧响应头白名单与响应体类型边界，认证/任意自定义头不会进入传输结果；新增凭证传播和异常响应负例。
- 2026-09-12：CLI 原子输出增加文件及全路径符号链接边界，覆盖 GitHub 快照、demo、history 与 baseline 输出；新增重定向负例。
- 2026-09-12：GitHub client 增加响应 JSON 的 64 层嵌套与循环结构边界，深层/循环响应 fail-closed 为 invalid_json；新增负例。
- 2026-09-12：Composite Action 的 GITHUB_OUTPUT 增加父目录符号链接边界，避免 runner 输出被重定向；新增 Action 路径安全负例。
- 2026-09-12：场景注册表校验增加 64 层嵌套与循环结构边界，内存注入数据 fail-closed；新增场景安全负例。

- 2026-09-12：收紧 GitHub 数组资源的隐私投影：issues、pull requests、reviews 和 releases 现在只保留固定的状态、编号、时间和计数字段，丢弃正文、用户/作者对象、标签、URL 与未知字段；新增原始记录投影负例，避免缓存保存不必要的 GitHub 内容。
- 2026-09-12：为内置三类演练增加结构化 Evidence 链：每条结果现在记录来源、字段、观测值和说明，并在 Markdown 报告中单独展示；旧的 DrillResult 调用保持兼容，证据仍经过既有递归脱敏。
- 2026-09-12：把 GitHub 数组资源的隐私白名单下沉到离线快照与缓存校验层：issues、pull requests、reviews 和 releases 的未知字段、正文和嵌套用户对象现在直接拒绝，新增快照/缓存原始记录负例，防止绕过网络客户端重新保存原始内容。
- 2026-09-12：收紧基线门禁的规则版本边界：不同 `rule_version` 产生的报告现在直接拒绝比较，避免规则变化被误报为分数回归或改进；新增跨版本负例并补充架构说明。
- 2026-09-12：补齐场景生态的只读贡献入口：新增 `validate-registry PATH` CLI 命令，复用版本化注册表校验器并返回明确成功/输入错误状态；新增命令契约负例和贡献文档，不执行 entrypoint 或公式。
- 2026-09-12：为 GitHub 元数据摘要增加独立 `metadata_evidence`：报告逐个记录资源的观测值及 `observed`/`partial`/`unknown` 状态，明确其只提供上下文、不改变本地评分，也不复制原始记录。
- 2026-09-12：补齐内存注入快照的循环结构边界：`validate_metadata()` 现在检测 dict/list 自引用并返回受控 `MetadataError`，不会让调用方遇到未处理的 `RecursionError`；新增循环结构负例。

- 2026-09-12：统一 GitHub 元数据快照的文件边界：普通 `--github-metadata` 输入现在与缓存一样拒绝符号链接、目录和其他非普通文件，并新增快照路径负例，避免隐私校验只覆盖缓存分支。

- 2026-09-12：收紧本地 GitHub 元数据缓存文件边界：读取与更新现在拒绝符号链接、目录和其他非普通文件，避免缓存路径被重定向到不受控目标或特殊文件；新增目录/符号链接负例。

- 2026-09-12：继续收紧 composite Action 的 `GITHUB_OUTPUT` 边界：仅拒绝路径符号链接不足以防止硬链接重定向；现在对已打开描述符校验普通文件与单链接计数，并在写入后 `fsync`，新增硬链接负例且保留失败时目标文件不变的证据。

- 2026-09-12：收紧 `continuity.json` 配置 schema：未知顶层字段和未知 `privacy` 选项现在明确拒绝，避免未来/拼写错误配置被静默忽略；新增配置负例。

- 2026-09-12：修复损坏 `package.json` 被静默视为“无依赖”的问题；JSON、顶层类型或 dependencies/devDependencies/peerDependencies 字段类型不合法时，分析器现在返回受控输入错误，避免错误的低风险结论，新增 3 类负例。

- 2026-09-12：修正发布验证脚本的默认产物目录为明确的 `D:/Codex/maintainer-zero-release-verify` 绝对路径，避免 Windows 反斜杠字符串在特定调用方式下被解释为项目内相对路径；新增默认路径契约测试。

- 2026-09-12：为只读 GitHub transport 增加安全 `repr`：调试输出只显示 `token_present`，不显示 token 内容；新增凭证泄露负例，避免异常诊断或日志意外暴露认证值。

- 2026-09-12：扩展报告递归脱敏：metadata 数组记录或嵌套对象中的 `token`、`secret`、`password`、`api-key`、`authorization` 等凭证键现在统一替换值为 `[REDACTED]`，新增 JSON/Markdown/HTML 负例，避免仅靠顶层 schema 防护。

- 2026-09-12：收紧本地分析器的符号链接边界：依赖清单、CODEOWNERS、工作流和发布文件只有在解析后仍位于仓库根目录内才会被读取或枚举；新增仓库外链接负例，避免扫描范围越界。

- 2026-09-12：为 GitHub 快照与缓存增加 64 层嵌套上限；极深 JSON 现在转为受控的 metadata/cache 错误，不会因递归深度触发未处理异常，新增文件快照与缓存负例。

- 2026-09-12：补齐 GitHub HTTP JSON 溢出数值边界：`1e999` 等解析为无穷浮点数的对象/数组响应现在统一降级为 `invalid_json`，不会在最终 schema 校验阶段冒出异常；新增两类负例。

- 2026-09-12：收紧只读 HTTP transport 的凭证与请求头边界：token 和 User-Agent 现在拒绝全部 ASCII 控制字符（不只 CR/LF），避免 NUL、TAB 等字符进入认证或请求头；新增负例测试。

- 2026-09-12：将 `init` 的 starter `continuity.json` 写入接入原子替换与失败清理边界；重复初始化保留用户配置，替换失败返回退出码 2 且不留下半成品，新增幂等与失败回归测试。

- 2026-09-12：收紧 GitHub 元数据顶层 schema，仅允许 schema_version、permissions、data、collection 和受限 cache envelope；token/secret 等任意凭证样字段会在快照校验和缓存保存阶段直接拒绝，而不是仅在摘要阶段隐藏；专项 34 项通过。
- 2026-09-12：收紧 composite Action 的 `GITHUB_OUTPUT` 边界：要求绝对路径，在 runner 提供 `RUNNER_TEMP` 时限制于该目录，拒绝控制字符、符号链接和缺失父目录，并使用 `O_NOFOLLOW` 打开输出文件；输出写入失败返回输入/环境错误码 2，新增契约负例覆盖。

- 2026-09-12：强化 GitHub 元数据缓存写入：改用同目录唯一临时文件、flush/fsync 与原子替换，避免并发运行共用固定 .tmp 文件；替换失败时保留旧缓存并清理临时文件，专项 33 项通过。

- 2026-09-12：收紧 GitHub 元数据的 JSON 数值边界：拒绝 NaN/Infinity 等非标准 JSON 数值，HTTP 采集的对象/数组响应统一降级为 invalid_json，内存注入快照也执行有限数值校验；专项 35 项通过。

- 2026-09-12：将 demo --output 纳入统一原子写入边界；新增写入失败时保留已有文件、并清理临时文件的回归测试，专项 10 项通过。

- 2026-09-12：将 CLI 生成的 history-summary.json 与 baseline-comparison.json 纳入同目录原子替换边界，避免中断时截断已有门禁/趋势证据；离线真实 Git fixture 新增回归覆盖，专项 18 项通过。

- 2026-09-11：修复 wheel/sdist 发布验证脚本的重复执行缺陷：只清理脚本生成的归档，安装探针使用每轮独立临时目录；新增幂等回归测试。CI 增加 Ubuntu/Python 3.12 的 release-smoke job，在源码树外构建、安装并运行两个打包工件；全量回归 151 项通过。该 job 只验证构建与安装，不发布 PyPI；真实 Marketplace/PyPI 发布和正式外部仓库验证仍待授权。

- 2026-09-11：新增 collect-github 的 max-response-bytes 显式收紧参数（1 至 1 MiB），并将同一上限传入 HTTP transport 与注入式客户端；149 项全量回归通过。真实 GitHub-hosted runner、外部 publisher、Marketplace/PyPI 和正式发布仍待完成。

- 2026-09-11：在 GitHub 只读采集边界中保留经过范围校验的 `Retry-After` / `X-RateLimit-Reset` 调度提示，并将其传入机器可读报告；不自动重试、不复制任意响应头。复合 Action 进一步把 `path`、`output`、`baseline` 和 `github-metadata` 全部限制在 workspace 内，拒绝控制字符和路径逃逸；离线集成测试与 137 项全量回归通过。真实 GitHub-hosted runner、外部 publisher、Marketplace/PyPI 和正式发布仍待完成。
- 2026-09-12：收紧趋势 Markdown 摘要的字段转义，覆盖反引号、链接、强调、HTML、反斜杠和表格分隔符；恶意场景名称只作为文本显示，不得改变摘要结构。
- 2026-09-12：在源码树外完成 wheel/sdist 双产物验证：两个归档均可隔离安装、导入包内模块并运行 3 场景 demo；验证产物写入 `D:/Codex/maintainer-zero-release-verify`，未发布到 PyPI。
- 2026-09-12：补齐自带 GitHub workflow 的恢复工件上传契约，JSON、Markdown、HTML、SARIF、Runbook、CODEOWNERS 草稿和 Issue 草稿现在一并进入 artifact；仍不写回仓库或 GitHub。
- 2026-09-12：修复源码树外 sdist 安装验证在干净环境中的离线缺口，安装探针显式禁用 build isolation；专项验证 3 项通过，避免隐式网络解析构建依赖。
- 2026-09-12：加固恢复工件文本边界：Runbook/Issue/CODEOWNERS 草稿对反引号、链接、强调、HTML 和表格符号做 Markdown 转义，并扩展 `authorization:` 凭证脱敏；新增恶意输入负例。
