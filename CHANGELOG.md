# Changelog

## Unreleased

- Continuity history reads now reject duplicate JSON keys and non-standard
  numbers, enforce the existing size bound before parsing, and recheck file
  identity, size, and mtime after descriptor reads so trend evidence fails
  closed if the history file is replaced during loading.

- Data-only demo suites and dependency fallback plans now reject ambiguous
  duplicate JSON keys and non-standard numbers; external demo files use the
  same bounded descriptor, link/special-file, and replacement-race checks as
  other local input artifacts, while fallback reads recheck mtime as well.

- `simulate --history` now reloads the generated report through the bounded
  report validator before appending trend history, so a report replaced by a
  link, special file, oversized payload, or concurrent rewrite cannot bypass
  the local input boundary.

- Repository declaration files used by the local analyzer (`package.json`,
  requirements files, CODEOWNERS, release files, and workflow YAML) now use
  bounded descriptor reads with link/special-file rejection and identity/mtime
  rechecks; ambiguous package JSON keys and non-standard numbers fail closed.

- Continuity configuration loading now rejects symlinked/reparse-point or
  special files, bounds input to 1 MiB, rejects duplicate keys and non-standard
  JSON numbers, and rechecks file identity, size, and mtime after reading.

- Credential creation now rejects output paths for any artifact already
  listed in the manifest, so it cannot invalidate newly bound evidence.

- Manifest verification now confirms that the manifest file remains the same
  regular file (including size and modification time) after every artifact is
  checked, closing a replacement window between manifest parsing and the final
  integrity result.

- The init command now rejects symlinked, reparse-point, and special output
  directories before creating a starter configuration, preventing a requested
  path from redirecting writes outside the selected repository.

- Action integration coverage now exercises the optional workspace-local `history` input end to end, including manifest and integrity-credential verification of trend sidecars.

- Release install probes now load the packaged scenario registry and data-only demo fixture,
  and compare installed distribution metadata with `maintainer_zero.__version__`,
  catching package-data or version-drift omissions that a module import alone would miss.
- sdist builds now run from an isolated, link-free source snapshot outside the checkout,
  preventing Windows build-backend cleanup races from locking or dirtying the working tree.
- Credential creation and verification now require the bound report to be an
  exact artifact-manifest entry (matching path, size, and SHA-256), so a valid
  manifest cannot silently omit the report covered by the credential.
- Release verification now rejects symlinked/reparse-point artifact wheelhouses
  and pre-existing linked archives before invoking build tools.
- Dangling wheelhouse links now fail with the same controlled safety error
  instead of falling through to directory creation.
- Post-build release archives are now rechecked for ordinary non-empty files,
  bounded size, and the expected wheel/sdist pair before installation probes.
- Installation probes now consume a privately staged archive copy after source
  identity/size/mtime checks, closing the post-validation replacement window.
- Staged release archives are now rehashed through stable descriptors and
  compared with their source bytes, detecting same-inode replacements that
  preserve size and timestamps.
- Release build and install probes now pass `--no-index` as well as bounded
  dependency/build-isolation flags, making the verification path explicitly offline.
- Release smoke now runs a full packaged `simulate` and verifies its manifest
  and integrity credential for both wheel and sdist installs.
- The release verifier CLI now converts validation and build exceptions into a
  stable exit code 2 and bounded error category for CI callers.

- Re-read credential inputs after manifest verification and fail closed when a report or manifest changes during creation, preventing known-stale integrity envelopes.

- Added offline `validate-benchmark` for strict, privacy-preserving benchmark summaries; rejects unsafe fields, duplicate keys, non-standard numbers, redirected files, and inconsistent aggregates before sharing.

- Added offline integrity credentials that bind `continuity.json` to the artifact manifest; verification is explicitly not a digital signature and now fail-closes on links, path escapes, control characters, output collisions, duplicate keys, deep JSON, and read races.
- Recursive response validators now preserve their active-node set when it is empty, so cycle detection remains correct for provider adapters and future in-memory transports.
- GitHub HTTPS transport now rejects config objects without the required fields with a bounded transport error instead of leaking an attribute exception, while preserving validation for compatible config objects.
- GitHub's explicit HTTPS transport now bounds API-base and User-Agent lengths and rejects control characters before constructing a request, matching the non-GitHub provider transports.
- GitHub's explicit HTTPS transport now bounds query components and the encoded query string, rejecting control characters and oversized URLs before invoking the opener.
- GitHub's injected read-only client now rejects duplicate JSON object keys and integers outside the signed 64-bit range before projection, matching the provider-neutral fail-closed boundary.
- GitLab release records now map the provider-specific `released_at` timestamp to the canonical `published_at` field, with an offline transport/client/cache regression covering projection and sensitive-field removal.
- Provider header parsing now rejects Unicode or oversized numeric hints safely and preserves a partial/page-limit result when GitLab advertises more pages than the local bound.
- Provider HTTPS transport now bounds API-base, User-Agent, query component, and encoded query lengths before invoking the opener.
- Provider pagination now honors bounded GitLab X-Next-Page headers in addition to Link headers, while preserving the fixed page-count limit.
- Added an offline provider-flow regression covering HTTPS transport, GitLab projection, canonical validation, cache persistence, and the CLI validator without connecting to a real service.
- collect-provider now validates cache TTL bounds before constructing a transport, so invalid cache configuration cannot trigger a network request or partial snapshot output.
- Provider collection now uses each adapter's bounded pagination contract (per_page for GitLab and limit for Forgejo), preventing ignored query parameters from silently changing page sizes.
- Added explicit collect-provider CLI support for GitLab and Forgejo. The command validates provider identifiers, HTTPS API bases, pagination/timeout/response bounds, and requires --allow-network; environment tokens remain opt-in and outputs/caches use the existing bounded atomic writers.
- Added offline `normalize_metadata()` mapping for reviewed GitHub, GitLab, and Forgejo adapter snapshots; explicit aliases map provider resources to canonical names while ambiguous, nested, unknown, or credential-like fields fail closed. This is not a network client.
- Added an injected, read-only GitLab/Forgejo provider client with explicit endpoint allowlists, bounded pagination, response sizes, timeout, rate-limit hints, and canonical projection; it performs no network I/O unless the caller supplies a transport and does not support writes or token loading.
- Provider adapter hardening now bounds integer projections and checks rate-limit header lengths before conversion, preventing oversized numeric inputs from crossing the canonical or scheduling boundaries.
- Added an opt-in stdlib HTTPS GET transport for GitLab and Forgejo with fixed provider paths, no redirects, bounded responses/timeouts/headers, and explicit `GITLAB_TOKEN`/`FORGEJO_TOKEN` environment opt-in.
- GitHub 只读采集器现在在规范化快照中显式写入 `provider: github`，与 provider-neutral 离线协议建立可审计连接；旧快照仍兼容默认 GitHub 语义。
- metadata cache 读取现在与普通快照一致拒绝重复 JSON key 与 NaN/Infinity，避免缓存 envelope 在校验前静默丢失字段或传播非标准数值。
- 新增 provider-neutral 离线元数据快照契约：可选 provider 为 github、gitlab 或 forgejo，沿用同一资源白名单、unknown/partial 语义和只读边界；新增 validate-metadata 命令。在该历史版本中尚未提供 GitLab/Forgejo 网络客户端，适配器仍需由调用方生成经过审阅的快照；后续版本已加入显式 opt-in 的 HTTPS GET transport 与 `collect-provider` CLI。
- baseline 报告 schema 现在验证每个结果的分数必须是有限且位于 0..100 的数值；非法超大整数、NaN/Infinity 与小数越界均 fail-closed，避免比较门禁泄漏异常或误读异常分数。
- benchmark 与 baseline 输入现在拒绝重复 JSON key、NaN/Infinity 和无法安全转换的超大整数；benchmark 文本渲染器也独立校验场景、分数、置信度与 Unicode 控制字符，避免不可信映射绕过 CLI 产生歧义或注入输出。
- 模拟输出新增本地 `artifact-manifest.json`，记录实际生成工件的相对路径、大小和 SHA-256；新增离线 `verify-manifest` 校验命令。manifest 拒绝路径逃逸、链接、特殊文件和超大输入，不包含自身 hash，也不被描述为数字签名或来源证明。
- composite Action 与 continuity workflow 现在暴露并上传 `artifact-manifest.json`；manifest 读取/哈希过程增加 descriptor 身份复核，路径替换竞态 fail-closed。
- 新增 `--fallback-plan` data-only 依赖替代/冷构建计划：严格校验来源、状态和重复项，并在 JSON/Markdown 报告中明确该计划未执行；不联网、不执行仓库命令。
- `verify-manifest` 读取 manifest 本身时现在也逐级拒绝链接/reparse 父目录，并复核打开描述符的身份、大小和修改时间；manifest 被替换或并发修改时 fail-closed。
- baseline 报告加载现在限制为有界普通文件，逐级拒绝链接/reparse 路径并复核打开描述符；报告被重定向、替换或超限时不会进入比较逻辑。
- 新增只读 `validate-fallback-plan` 命令，可在注入演练报告前单独校验 data-only 依赖替代/冷构建计划；输出明确 `execution: not-run`，不会执行命令或联网。
- GitHub 离线快照读取后现在复核身份、大小与修改时间，并拒绝重复 JSON key，避免同一次元数据读取混入被替换或含歧义的声明。
- 修复同一输出目录的 baseline 演练：CLI 现在在替换新报告前加载并保留旧 baseline，避免 `--baseline OUTPUT/continuity.json` 被新报告覆盖后错误显示为 unchanged。
- 新增隐私保护 `export-benchmark`：从已验证报告生成不含仓库/人员身份、依赖名、Finding 文本或原始记录的固定摘要，并明确该摘要不是跨项目排名。

本文件记录尚未发布的本地开发版本；项目当前没有公开远程仓库或已发布包。


- composite Action 的 `GITHUB_OUTPUT` 契约测试现在覆盖 Windows reparse point 父目录和目标文件，确保 runner 输出不会被重定向或覆盖特殊文件。
- 报告三文件现在采用可回滚的整套原子替换；中途失败会恢复旧的 JSON/Markdown/HTML 组合，不留下新旧报告混合状态。
- 报告生成现在会在首次替换前预检 `continuity.json`、Markdown 和 HTML 三个目标，任一目标为符号链接、reparse point 或特殊文件时整体拒绝，避免留下半套报告。
- 社区场景注册表与 data-only 场景加载器现在也拒绝 Windows junction/reparse point（不仅是 POSIX 符号链接），并增加跨平台路径模拟负例，避免贡献校验被重定向到未审阅目标。
- 恢复工件现在会在移动任一暂存文件前预检整套目标，拒绝符号链接、reparse point 和特殊文件，避免多文件原子替换在冲突目标下留下半套输出。
- 报告与 history 输出现在复用逐级安全目录检查，拒绝父目录符号链接/reparse point、特殊文件和超大 history，避免趋势或报告证据被重定向。
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
