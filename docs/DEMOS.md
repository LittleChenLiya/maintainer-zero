# 可复现事故前/改进后 demos

`examples/demos/continuity-demos.json` 是纯数据 fixture，包含三个本地演示：维护者交接、
依赖冷构建和 CI/发布 fallback。每个 demo 都提供两个 `RepoSnapshot`，runner 只调用
项目内置的确定性场景函数，不执行 fixture 中的路径、脚本或命令，也不联网。

可直接通过 CLI 运行整套演示；命令不要求当前目录是 Git 仓库：

```powershell
maintainer-zero demo
maintainer-zero demo --format json --output .continuity/demo.json
```

`demo` 默认输出可读摘要，`--format json` 输出版本化结果。`--fail-on-regression`
可用于 CI：只要任一“改进后”分数没有高于“事故前”，命令就以退出码 1 结束；输入
错误使用退出码 2。`demo` 与 `demos` 是同义命令。

不带路径时，CLI 从已安装包内的 `maintainer_zero/continuity_demos.json` 读取内置
fixture，因此在任意工作目录、隔离安装和源码树外都可运行。传入路径仍可运行经审阅的
本地 data-only suite。JSON 输出的顶层契约是 `schema_version` 与 `results`；输入 fixture
仍使用 `schema_version` 与 `demos`。

Demo 文件是受限的 JSON 数据：只允许内置场景和快照字段，不执行路径、命令或脚本。
加载器限制文件大小为 1 MiB、最多 10 个 demo；计数、列表、文本和 ID 都有边界，
贡献者计数不能超过提交总数。

运行测试即可验证三个改进后的分数都高于事故前：

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
python -m pytest tests/test_demos.py -q
```

也可以直接运行离线 CLI，结果只写入指定的本地 JSON：

```powershell
maintainer-zero demo examples/demos/continuity-demos.json --output .continuity/demo-results.json
```

这些分数是解释性演练结果，不是事故概率、认证或跨项目排名。
