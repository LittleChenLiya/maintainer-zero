# 发布前验证清单

本项目当前尚未发布包或创建公开远程仓库。每次准备发布候选版本时，在本地执行：

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
python -m pytest -q
python -m compileall -q maintainer_zero
python tools/verify_release.py --output D:/Codex/maintainer-zero-release-verify
python -m pip install --no-deps --no-build-isolation --target D:\Codex\maintainer-zero-wheel-install <wheel-or-sdist>
$env:PYTHONPATH='D:\Codex\maintainer-zero-wheel-install'
python -m maintainer_zero validate-scenario examples/scenarios/security-advisory-flood.json
python -m maintainer_zero demo --format json --fail-on-regression
python -m maintainer_zero verify-manifest .continuity/artifact-manifest.json
python -m maintainer_zero verify-credential .continuity/continuity-credential.json
```

复合 GitHub Action 还必须通过本地契约和集成检查：

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
python -m pytest -q tests/test_action_contract.py tests/test_action_integration.py tests/test_workflow_contract.py
```

这组测试使用离线临时 Git 仓库和本地缓存，覆盖 Unix/Windows 共用的 argv
适配器、报告输出、fail-under、baseline 回归门禁及过期元数据的显式授权。
它不等价于真实 GitHub Actions Ubuntu/Windows runner 验证；发布前仍需在受控远程
runner 上验证安装、GITHUB_OUTPUT 解析和矩阵行为。

安装验证必须使用源码树外的隔离目录，并至少确认 CLI 可导入、一个社区场景可校验、
以及内置注册表可加载。验证目录是临时产物，不应提交到 Git。
发布脚本的 wheel 构建与安装探针均使用 `--no-index`、`--no-deps` 和 `--no-build-isolation`，
确保这条本地证据不会因构建依赖或安装元数据解析而访问包索引。
发布验证 CLI 对输入、输出边界和构建阶段异常统一返回 2，并只输出稳定错误类别，便于 CI 调用方区分验证失败与成功。sdist 构建从源码树外的临时、无链接源码快照执行，避免 setuptools 在 Windows 上创建/删除临时包树时受工作树文件锁影响；快照会拒绝符号链接、reparse point 和特殊文件。
脚本会构建一个 wheel 和一个 sdist，在源码树外分别安装，并确认包内版本化 scenario
registry、data-only demo fixture 均可加载；并确认发行版元数据版本与 `maintainer_zero.__version__` 一致，
随后确认默认 `demo` 从包内 fixture 读取、
输出 3 个结果且通过回归门禁；随后用每个已安装归档运行完整 `simulate`，
生成并离线验证 `artifact-manifest.json` 与 `continuity-credential.json`。输出目录是临时产物，不应提交到 Git。

每次模拟还应验证 artifact manifest：它只记录本轮实际生成工件的相对路径、大小和 SHA-256，
不包含自身摘要；这是完整性校验，不是签名或来源证明。manifest 校验必须离线完成，失败返回 2。
模拟输出中的 integrity credential 进一步绑定报告与 manifest 的内容摘要；它同样不是数字签名，
不证明发布者身份或来源可信度。验证失败返回 2。验证时还应确认凭证文件及父目录为普通路径，
并拒绝控制字符、Windows 驱动器路径、输出覆盖输入和读取竞态。

ci.yml 的 release-smoke job 会在 Ubuntu/Python 3.12 runner 上重复执行同一发布验证脚本，
构建 wheel 和 sdist，并在源码树外安装后运行打包后的 demo。该 job 只验证构建和安装，
不发布到 PyPI；Windows/Python 矩阵仍由主测试 job 覆盖，真实 Marketplace/PyPI 发布仍需
单独授权和审核。

## Composite Action 本地验收

在声明 Action 可发布前，还应检查：

- `action.yml` 能被静态解析，`using: composite`、输入/输出名称、Unix `bash` 与 Windows `pwsh` 两条路径保持一致。
- `tools/action_entrypoint.py` 将路径、基线和元数据作为独立 argv 值传递，并把 `path`、`output`、`baseline`、`github-metadata` 都限制在 GitHub workspace 内；路径包含空格、`$`、分号或反斜杠时不产生 shell 插值。
- `collect-github --max-response-bytes N` 只能把单响应上限收紧到 `1..1,000,000` 字节；越界输入必须以退出码 2 拒绝，超大响应必须降级为 `response_too_large`，不能解析截断 JSON。
- Unix 与 Windows 适配器都只运行本地 CLI，不读取 `GITHUB_TOKEN`、不启用网络、不执行 GitHub 写入；默认只写配置的报告目录。
- 成功运行才写入 `GITHUB_OUTPUT`；七个 Action 输出必须指向同一输出目录下的绝对报告/恢复路径。
- 生成报告后先运行 `python -m maintainer_zero validate-report`；该检查覆盖有界 JSON、schema/数值边界、重复场景和重复 finding 标识，但不替代对仓库字段、证据和隐私声明的人工审阅。
- Windows workflow 必须在每个原生 Python verifier 后立即检查并传播 `$LASTEXITCODE`，避免后续成功命令掩盖报告、manifest 或 credential 校验失败。
- 失败路径的 job summary 可以使用 `always()` 保留诊断；正式 artifact 上传应使用 `success()`，不得把未通过校验的 bundle 当作已验证发布物。
- `validate-report` 必须拒绝空 `results` 或缺失 `score` 的结果；否则 baseline 比较可能把不完整输入当作无回归。
- `GITHUB_OUTPUT` 必须是绝对路径；在 GitHub runner 提供 `RUNNER_TEMP` 时，输出文件必须位于该临时目录内，拒绝控制字符、符号链接、硬链接、非普通文件和缺失父目录，打开后还要校验文件身份并 `fsync`，避免通过输出文件重定向写入任意路径或留下半写入结果。
- 发布验证脚本的输出目录及 `artifacts` wheelhouse 逐级拒绝 POSIX 符号链接、Windows junction/reparse point 和特殊文件（包括 dangling link）；构建前后都检查归档必须是非空、大小有界的普通 wheel/sdist 文件，并在每个安装探针前复制到独立稳定副本。复制后还会通过稳定描述符重新计算源归档和副本的 SHA-256，避免仅靠 inode、大小和 mtime 漏过同 inode 的内容替换。
- 本地契约测试覆盖成功产物、`--fail-under`/基线门禁失败、过期元数据默认拒绝及显式允许、以及含空格路径。真实 GitHub-hosted runner（Ubuntu/Windows 和 Python 矩阵）仍需在 CI 中验证，不能用本地测试替代。
- 启用 Action 的 `history` 输入时，还应确认 `history-summary.json` 与 `history-summary.md` 出现在 manifest、credential 验证和上传 artifact 中；历史文件必须位于 workspace 内。
- `init` 创建的 starter `continuity.json` 必须原子替换；重复运行不得覆盖用户配置，写入失败不得留下半成品或临时文件。

Action 调用方应固定经过审阅的 tag 或 commit，保留 `contents: read`，并避免在不可信 fork 场景使用 `pull_request_target`。
