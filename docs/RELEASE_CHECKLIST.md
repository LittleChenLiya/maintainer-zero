# 发布前验证清单

本项目当前尚未发布包或创建公开远程仓库。每次准备发布候选版本时，在本地执行：

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
python -m pytest -q
python -m compileall -q maintainer_zero
python -m pip wheel . --no-deps --no-build-isolation --wheel-dir D:\Codex\maintainer-zero-wheelhouse
python -m pip install --no-deps --target D:\Codex\maintainer-zero-wheel-install <wheel>
$env:PYTHONPATH='D:\Codex\maintainer-zero-wheel-install'
python -m maintainer_zero validate-scenario examples/scenarios/security-advisory-flood.json
```

安装验证必须使用隔离目录，并至少确认 CLI 可导入、一个社区场景可校验、
以及内置注册表可加载。验证目录是临时产物，不应提交到 Git。
