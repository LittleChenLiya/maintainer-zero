# 可复现事故前/改进后 demos

`examples/demos/continuity-demos.json` 是纯数据 fixture，包含三个本地演示：维护者交接、
依赖冷构建和 CI/发布 fallback。每个 demo 都提供两个 `RepoSnapshot`，runner 只调用
项目内置的确定性场景函数，不执行 fixture 中的路径、脚本或命令，也不联网。

运行测试即可验证三个改进后的分数都高于事故前：

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
python -m pytest tests/test_demos.py -q
```

这些分数是解释性演练结果，不是事故概率、认证或跨项目排名。
