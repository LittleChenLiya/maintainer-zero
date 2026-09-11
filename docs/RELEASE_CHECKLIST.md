# 发布前验证清单

本项目当前尚未发布包或创建公开远程仓库。每次准备发布候选版本时，在本地执行：

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
python -m pytest -q
python -m compileall -q maintainer_zero
python tools/verify_release.py --output D:\Codex\maintainer-zero-release-verify
python -m pip install --no-deps --target D:\Codex\maintainer-zero-wheel-install <wheel-or-sdist>
$env:PYTHONPATH='D:\Codex\maintainer-zero-wheel-install'
python -m maintainer_zero validate-scenario examples/scenarios/security-advisory-flood.json
python -m maintainer_zero demo --format json --fail-on-regression
```

安装验证必须使用隔离目录，并至少确认 CLI 可导入、一个社区场景可校验、
以及内置注册表可加载。验证目录是临时产物，不应提交到 Git。
脚本会构建一个 wheel 和一个 sdist，在源码树外分别安装，并确认默认 `demo` 从包内
fixture 读取、输出 3 个结果且通过回归门禁。输出目录是临时产物，不应提交到 Git。
