# 长期目标：将 Maintainer-Zero 做成可信、可复用的开源连续性演练工具

- 2026-09-15：补齐 GitHub 社区健康入口：新增 SUPPORT.md、Issue 分流配置和 README 社区说明，将问题、场景提案及安全/隐私反馈导向合适渠道，避免公开请求泄露敏感工件。

- 2026-09-14：Composite Action 改为通过 `PYTHONPATH` 直接运行 checkout 中的代码，不再要求 runner 预装 setuptools 或执行本地包构建；发布验证仍单独覆盖 wheel/sdist。

- 2026-09-14：新增配置路径回归，覆盖 `linked-parent/../linked-parent` 这类会在词法归一化后重新指向链接的写法，确认 `continuity.json` 读取在归一化前拒绝隐藏的 symlink/reparse point。

- 2026-09-14：发布验证器对源码、输出和 checkout 目录在逐组件检查后才归一化 `..`，防止 `link/../target` 隐藏链接组件；新增发布路径回归。

- 2026-09-14：发布源码快照改用不解析链接的词法 containment 检查，再执行 `lstat()`/描述符校验；避免仅为判断 checkout 归属而先跟随枚举条目。

- 2026-09-14：发布验证输出目录的二次校验改用 `lstat()` 组件检查，不再用 post-check `resolve()` 跟随可能被替换的链接；输出路径即使指向 checkout 外部也不会因此绕过 no-follow 约束。

- 2026-09-14：simulate 不再在加载 `continuity.json` 前提前 `resolve()` 仓库路径；配置读取器先逐组件检查再词法归一化，避免链接加 `..` 绕过配置边界。

- 2026-09-14：发布验证的隔离源码快照排除 `__pycache__`，避免测试导入在验证期间更新缓存目录元数据导致幂等构建误报源代码变化。

- 2026-09-14：baseline、benchmark、demo suite 与 fallback plan 的离线读取器在归一化 `..` 前逐级检查父目录，避免链接父级绕过 artifact 边界；专项测试保持通过。

- 2026-09-14：完整性凭证的输入、输出及验证路径在归一化 `..` 前逐级检查，避免链接父目录绕过边界；新增隐藏链接回归，凭证仍保持离线内容完整性而非签名声明。

- 2026-09-14：分析器仓库根路径在词法归一化前逐组件检查，防止 `link/../repo` 隐藏链接父级；新增回归并确认真实目录的正常 `..` 遍历仍可用。

- 2026-09-14：history 追加分支改用不跟随链接的 `lstat()` 观察，并拒绝非规则文件目标，避免文件在预检期间消失或被替换时误判为新 history；history 读写专项保持 fail-closed。

- 2026-09-14：原生 CLI 输出路径现在在词法归一化前逐级检查组件，避免通过 `..` 隐藏 symlink/reparse point；新增文件与目录目标回归，保持正常 parent traversal 可用。

- 2026-09-14：Composite Action 的 `GITHUB_OUTPUT` 在打开前拒绝特殊文件（包括可能阻塞的 FIFO），并捕获输出文件及父目录链身份；打开后复核身份，最终文件或父目录并发替换会 fail-closed，不会向替换目标追加结果。

- 2026-09-14：demo 输出移除安全检查前的递归父目录创建，避免链接父目录下的嵌套输出先在外部创建目录；不安全输出路径统一返回 CLI 错误码 2，并新增保留外部目录与异常转换回归。

- 2026-09-13：模拟入口在分析前预检 history 与自定义 recovery 输出的词法冲突，避免输出文件互相覆盖；GitHub/provider 的 output/cache 比较不再跟随链接，manifest 核心工件缺失时不再静默降级；报告派生 metadata evidence 复用凭证脱敏与 Markdown 转义边界。

- 2026-09-13：修正 manifest 门禁回归 fixture，使其在临时目录初始化真实 Git 仓库，与分析器拒绝非 Git 输入的契约保持一致。

- 2026-09-13：收紧 composite Action 的输入路径边界：workspace、仓库、输出、baseline、metadata、history、fallback plan 与 runner 临时目录现在使用不跟随链接的词法绝对路径，并逐组件拒绝符号链接、junction/reparse point 和非目录父级；新增 workspace/runner-temp 链接负例。

- 2026-09-13：本地 Git 分析现在要求 checkout 内的目录型 `.git` 元数据，拒绝 linked worktree 的 `.git` 文件；并在 Git 历史采集前后比较 `HEAD` 与完整 refs 摘要，分支或 ref 在分析期间变化时 fail-closed，避免把不同历史状态拼成一个快照。

- 2026-09-13：Action 路径检查会保留 `..` 组件直到逐级 `lstat` 完成，避免通过“链接目录/..”把符号链接藏在词法归一化之前；新增该顺序的回归覆盖。

## 总目标

2026-09-14：自带 CI 与 continuity workflow 升级到官方 Node.js 24 兼容的 actions/checkout、actions/setup-python 和 actions/upload-artifact v7，消除公开运行中的 Node.js 20 弃用警告；权限、只读边界和 artifact 验证契约保持不变。

2026-09-15：补全 pyproject.toml 的公开仓库、Issue、Discussion、作者、关键词和 alpha 分类元数据，并用测试锁定链接与 Python 版本边界；尚未发布 PyPI 包，正式发布仍需单独授权。

2026-09-15：新增标准 `CITATION.cff`，固定 0.2.0 版本、仓库链接、许可证和 alpha 项目摘要，并在测试中锁定关键字段，方便研究、文档和公开 benchmark 进行可追溯引用。

把 `D:\maintainer-zero` 从本地启发式 MVP 推进到可用于真实 GitHub 仓库的连续性灾难演练平台。每个阶段必须交付可运行代码、自动化测试、可解释报告、明确的隐私边界和文档，并在本地 Git 中形成独立提交。

最终用户应能在 5 分钟内完成一次演练，回答：核心维护者、关键依赖或 CI/发布链路失效后，哪些能力会中断、多久开始积压、有哪些可验证的恢复路径、应先补齐哪些责任与文档。

当前增量：模拟输出附带 `artifact-manifest.json`，可用 `verify-manifest` 在本地离线校验大小与 SHA-256。它不包含自身 hash，不是数字签名，也不证明来源可信。

2026-09-13：分析器入口现在逐级拒绝 symlink/reparse/special repository 路径，并在 Git 探针与声明文件扫描后复核根目录身份、大小和 mtime，避免将链接目标或并发替换误当作用户选择的 checkout。

2026-09-13：分析器声明路径现在逐级检查父目录链接；支持 `dir_fd` 的平台会从稳定的
目录描述符打开每个组件，避免父目录并发替换把读取重定向到 checkout 外。Windows 等不
支持该接口的平台继续使用 `O_NOFOLLOW` 与身份/mtime 复核的安全回退。

2026-09-13：发布验证的 wheel 与 sdist 现在统一从同一个无链接源码快照构建，避免构建后端直接执行 live checkout；这仍是本地隔离烟测，不替代真实 CI runner 或签名发布。

2026-09-13：发布验证的源码快照现在逐级拒绝链接/reparse/special checkout 路径；目录枚举后复核身份与修改时间，普通文件通过 `O_NOFOLLOW` 描述符复制并在替换前后复核，避免并发变化将隔离构建重定向到 checkout 外。该保护仍不替代真实 GitHub runner 或签名验证。

2026-09-13：发布安装烟测的完整 `simulate` 现在针对每个临时安装目录内新建的空 Git 仓库执行，不再把 live checkout 作为已构建发行版的输入，避免源码快照完成后再次打开可变工作树。

2026-09-13：源码快照复制还保留主机可表达的普通文件权限位，避免隔离构建让可执行打包脚本静默失去执行属性；Windows 仍受其文件权限语义限制。

2026-09-13：源码快照复制还保留普通文件的访问/修改时间，并使用不跟随链接的更新方式，避免隔离构建仅因快照时刻改变 timestamp-sensitive 包元数据。
2026-09-13：源码快照时间戳复制兼容部分 Windows Python 构建中 `follow_symlinks=False` 不可用的实现，仍在发布临时快照前复核其描述符和路径身份；这只是本地兼容性与竞态防护，不替代签名验证。

2026-09-13：`continuity.json` 读取现在采用有界、fail-closed 文件边界：拒绝符号链接、Windows reparse point 和特殊文件，限制 1 MiB 大小，拒绝重复键与 NaN/Infinity，并在读取后复核文件身份、大小和 mtime，避免配置竞态改变演练结论。

2026-09-13：本地分析器读取 `package.json`、`requirements*.txt`、CODEOWNERS、发布配置和
工作流 YAML 时也采用有界描述符读取，拒绝链接/特殊文件并复核身份、大小和 mtime；依赖
清单 JSON 的重复键和非标准数值会 fail-closed。声明文件超限或在读取期间变化时，演练
不会把缺失数据误判为低风险。

2026-09-13：同仓库趋势历史读取现在同样拒绝重复 JSON 键与 NaN/Infinity，先执行大小
上限检查，并在描述符读取后复核文件身份、大小和 mtime；历史文件替换或重写期间会
fail-closed，避免趋势摘要来自不一致的证据。

2026-09-13：`simulate --history` 追加趋势前改用与 baseline 相同的有界报告加载器，
避免输出报告在生成后被替换为链接、特殊文件、超限内容或并发重写时绕过输入校验。

2026-09-13：data-only demo 与依赖 fallback 计划的 JSON 读取现在拒绝重复键和
NaN/Infinity；外部 demo 文件使用有界描述符读取并复核替换竞态，fallback 计划
额外复核读取后的 mtime，避免声明性证据在加载窗口内被静默替换。
manifest 校验会在全部工件检查完成后再次确认 manifest 文件身份、大小和修改时间未变化；期间发生替换或重写会 fail-closed。
当前增量同时附带 `continuity-credential.json`：它以独立 envelope 绑定报告和 manifest 的大小、SHA-256 及组合摘要，支持 `verify-credential` 离线校验。该凭证明确不是数字签名，不证明来源、身份或授权。
GitHub composite Action 也暴露该 manifest 的绝对路径并将其纳入连续性 workflow artifact；Action 仍只做本地分析，不上传源码或执行 GitHub 写操作。
创建凭证时会在 manifest 校验后重新读取并比较报告与 manifest；发现校验窗口内的替换或内容变化即 fail-closed，避免生成已知过期的凭证。该检查不提供并发写入锁，也不改变“不是数字签名”的边界。
凭证创建与验证还要求报告本身是 manifest 的精确条目（路径、大小和 SHA-256 一致）；遗漏报告的独立 manifest 会被拒绝，避免完整性声明出现未覆盖的核心工件。
发布验证脚本现在把源码树外的 `artifacts` wheelhouse 作为独立安全目录检查，拒绝 POSIX 符号链接、Windows junction/reparse point、特殊文件及链接归档；本地契约覆盖这些边界，但不替代真实 runner 验证。
补充覆盖 dangling wheelhouse link：即使目标已失效也会被识别为 unsafe，而不会落入 `mkdir` 的非受控异常路径。
构建后还会重新检查 wheel/sdist 数量、后缀、普通文件属性和 128 MiB 大小上限，避免特殊文件或异常归档被送入安装烟测。
每个安装探针现在只使用经过源文件身份/大小/修改时间复核的临时归档副本，隔离校验完成后的替换窗口；副本仍不构成签名或来源证明。
复制后还会通过稳定描述符重新计算源归档与副本的 SHA-256，检测同 inode、同大小且恢复修改时间的内容替换；该校验仍不提供来源或发布者证明。
发布验证的构建与安装命令还显式禁用包索引访问（`--no-index`），使离线证据不依赖网络可用性。
每个 wheel/sdist 的隔离安装探针现在还直接加载打包后的版本化 scenario registry 与 data-only demo fixture，并比较发行版元数据版本与运行时 `maintainer_zero.__version__`，再运行完整三场景 `simulate`，用安装包自身的 CLI 离线验证 manifest 与 integrity credential，覆盖最终用户主路径而不读取源码树中的包。
发布验证入口现在对安全边界和构建异常提供受控退出码 2 与稳定错误类别，便于 CI 自动化消费。
init 入口现在也逐级检查目标目录，拒绝符号链接、Windows reparse point 和特殊文件后才创建 starter 配置，避免初始化写入被重定向到目标之外。

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
- [x] 整理英文 README、中文指南、变更日志和可复制的 launch kit；GitHub 公开仓库与 Discussions 首帖已发布。
- [ ] 发布经过用户确认的 PyPI 包和 Marketplace Action，并将版本标签、安装说明与发布验证结果对齐。

## 执行规则

- 一次推进一个可以验收的增量，先修复影响结论可信度的问题，再扩展传播功能。
- 多 agent 只承担边界明确的模块；共享文件由主代理整合，避免并发覆盖。
- 每轮记录：完成内容、验证结果、剩余风险、下一项。
- 本地实现与测试可自主推进；创建公开远程仓库、push、发布包、发布报告、花费或修改真实项目权限，必须另获用户授权。
- 遇到技术失败先排查与降级；只有需要新增权限或外部决策时才停下询问。

### 离线端到端证据

tests/test_e2e_fixture.py 使用真实 Git 历史的最小仓库 fixture，验证本地分析、三类演练、脱敏报告、恢复工件、基线比较以及依赖膨胀后的回归门禁。该测试不联网、不读取 token，所有输出仅写入临时目录；详见 E2E_FIXTURE.md。

## 当前执行记录

- 报告校验摘要的规则、工具和场景标识均限制为有界可打印文本，防止不可信报告污染终端输出。
- 自带 continuity workflow 在 Unix/Windows 两侧先执行 `validate-report`，再核验 manifest 与 credential；重复场景或 finding ID 会 fail-closed。
- Windows 校验步骤在每个原生 Python verifier 后立即传播 `$LASTEXITCODE`；单个报告、manifest 或 credential 验证失败都会使步骤失败，不会被后续成功命令掩盖。
- continuity workflow 仅在输出、报告、manifest 和 credential 校验成功后上传工件；失败路径仍保留 job summary 诊断，但不发布未验证工件。
- 报告校验现在要求至少一个场景结果，且每个结果必须包含 0–100 的有限数值分数，避免不完整 baseline 被误判为无回归。
- 报告 finding 严重级别现在限制为 `info`、`low`、`medium`、`high`、`unknown`（不区分大小写），避免未知级别绕过高风险门禁。
- 报告结果若声明 `confidence`，现在只允许 `high`、`medium`、`low`、`unknown`；缺失字段的旧报告继续兼容读取，未知值、空字符串和非字符串值 fail-closed，避免把未经定义的可信度当作证据。

- 2026-09-14：新增离线 `validate-report` 入口，复用基线比较的有界报告读取与 schema/数值校验；输出仅包含 schema、规则版本、场景分数/计数和覆盖摘要，不包含仓库路径或原始 finding，便于分享前和 CI 预检。

以下条目按日期保留历史状态；早期条目中“尚未提供 GitLab/Forgejo 网络客户端”仅适用于
当日版本，已由后续的 HTTPS GET transport 与 `collect-provider` 条目取代，不代表当前能力。

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
- 2026-09-13：新增离线 provider 采集链回归：fake HTTPS opener → GitLab 字段投影 → canonical 校验 → cache → validate-metadata CLI；验证分页参数、敏感字段剔除和无真实网络连接。
- 2026-09-13：补齐 GitLab 的 X-Next-Page 分页提示，按有界页码与固定 max-pages 识别短页后的下一页；Forgejo 继续使用 Link: rel="next"，并新增 transport/header 回归。
- 2026-09-13：provider HTTPS transport 增加 API base、User-Agent、查询参数及编码查询串长度上限；超限输入在 opener 调用前 fail-closed，并补充直接 API 负例。
- 2026-09-13：加固 provider 分页与限流头解析：仅接受 ASCII 数字，GitLab 超出本地 max-pages 时保持 partial/page-limit；新增 Unicode、超长及页界限回归。
- 2026-09-13：补齐 GitLab release 字段差异：将 API 的 `released_at` 映射为规范化 `published_at`，并用离线 transport/client/cache 链路验证字段投影与敏感字段剔除。
- 2026-09-13：统一 GitHub 注入式客户端与其他 provider 的 fail-closed 解析边界：重复 JSON key 和超出 64 位的整数现在在字段投影前降级为 invalid_json，并补充直接客户端负例。
- 2026-09-13：补齐 GitHub HTTPS transport 的查询边界：参数组件和编码后的 query string 现在有固定长度上限，控制字符或超长 URL 在 opener 调用前拒绝，并补充直接 transport 负例。
- 2026-09-13：统一 GitHub 与其他 provider 的 transport 配置边界：API base 和 User-Agent 现在有固定长度并拒绝控制字符，避免不安全配置进入请求构造。
- 2026-09-13：GitHub HTTPS transport 对缺少必要字段的 config 现在统一 fail-closed 为受控 transport 错误，避免把 AttributeError 泄漏给上层集成，同时保留兼容配置对象的字段校验；新增直接构造负例。
- 2026-09-13：修正 GitHub 与 GitLab/Forgejo 响应递归校验器在空活动集合上的初始化逻辑，确保循环检测状态不会被错误重置；保持解析边界 fail-closed。
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
- 2026-09-12：连续性 workflow 的失败诊断摘要使用 `always()`；正式 artifact 上传后来收紧为仅在验证成功时执行，避免将未验证 bundle 与诊断输出混淆。
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
