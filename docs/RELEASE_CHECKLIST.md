# 发布前验证清单

本项目当前尚未发布包或创建公开远程仓库。每次准备发布候选版本时，在本地执行：

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
python -m pytest -q
python -m compileall -q maintainer_zero
python tools/verify_release.py --output D:/Codex/maintainer-zero-release-verify
python -m pip install --no-deps --target D:\Codex\maintainer-zero-wheel-install <wheel-or-sdist>
$env:PYTHONPATH='D:\Codex\maintainer-zero-wheel-install'
python -m maintainer_zero validate-scenario examples/scenarios/security-advisory-flood.json
python -m maintainer_zero demo --format json --fail-on-regression
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

安装验证必须使用隔离目录，并至少确认 CLI 可导入、一个社区场景可校验、
以及内置注册表可加载。验证目录是临时产物，不应提交到 Git。
脚本会构建一个 wheel 和一个 sdist，在源码树外分别安装，并确认默认 `demo` 从包内
fixture 读取、输出 3 个结果且通过回归门禁。输出目录是临时产物，不应提交到 Git。

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
- 成功运行才写入 `GITHUB_OUTPUT`；`report-directory` 与 `report-json` 必须指向同一输出目录下的绝对路径。
- `GITHUB_OUTPUT` 必须是绝对路径；在 GitHub runner 提供 `RUNNER_TEMP` 时，输出文件必须位于该临时目录内，拒绝控制字符、符号链接和缺失父目录，避免通过输出文件重定向写入任意路径。
- 本地契约测试覆盖成功产物、`--fail-under`/基线门禁失败、过期元数据默认拒绝及显式允许、以及含空格路径。真实 GitHub-hosted runner（Ubuntu/Windows 和 Python 矩阵）仍需在 CI 中验证，不能用本地测试替代。
- `init` 创建的 starter `continuity.json` 必须原子替换；重复运行不得覆盖用户配置，写入失败不得留下半成品或临时文件。

Action 调用方应固定经过审阅的 tag 或 commit，保留 `contents: read`，并避免在不可信 fork 场景使用 `pull_request_target`。
