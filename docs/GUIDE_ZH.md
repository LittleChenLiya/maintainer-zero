# Maintainer-Zero 中文使用指南

Maintainer-Zero 是一个本地优先的开源项目连续性演练工具。它把维护者不可用、依赖撤包和 CI/发布中断转换成可解释的时间线、评分与恢复建议。结果是启发式演练，不是安全认证、事故概率或合规结论。

## 五分钟开始

在已安装项目中执行：

```powershell
maintainer-zero simulate . --scenario all --output .continuity
```

查看 `.continuity/report.md`、`.continuity/report.html` 和 `.continuity/recovery/` 下的恢复草稿。CLI 默认只读取本地 Git，不上传仓库内容，也不会写入 GitHub。
如需保存同仓库趋势，可增加 `--history .continuity/history.json`；输出目录会同时生成机器可读的 `history-summary.json` 和不含本地路径的 `history-summary.md`。未知值保持为 `unknown`，不代表零风险。

贡献场景时可用 `maintainer-zero describe-scenario PATH --format json` 生成只读契约摘要，审阅输入来源、恢复动作和限制；它不会执行 entrypoint、公式或仓库代码。

首次为其他仓库生成配置：

```powershell
maintainer-zero init D:\path\to\repo
maintainer-zero simulate D:\path\to\repo --scenario all --days 90
```

## CI 门禁与基线

```powershell
maintainer-zero simulate . --scenario all --fail-under 70
maintainer-zero simulate . --baseline .continuity/continuity.json --fail-on-score-decrease
maintainer-zero simulate . --baseline .continuity/continuity.json --fail-on-new-high-risk
```

退出码为 0（通过）、1（门禁失败）或 2（输入错误）。分数比较只能说明当前规则和输入快照下的变化。

## 离线 Demo

```powershell
maintainer-zero demo
maintainer-zero demo --format json --output .continuity/demo.json --fail-on-regression
```

不带路径时使用安装包内的 data-only fixture，因此不要求当前目录是 Git 仓库。传入本地 JSON 前应审阅其内容；加载器不会执行路径、命令或脚本字段。

## GitHub 元数据

可以把已审阅的只读快照传给 `--github-metadata`。当前实现不自动读取 token，不默认联网，不修改 Issue、PR、权限或仓库文件。标准库 GET transport 需要调用方显式 opt-in，并限制 HTTPS、GET、白名单路径、超时和响应大小。

如需从真实仓库生成快照，必须显式允许网络：

```powershell
maintainer-zero collect-github octo-org/example --allow-network --output github-metadata.json
maintainer-zero simulate . --github-metadata github-metadata.json --output .continuity
```

如需审阅单个 PR 的评论/评审元数据，可显式指定 `--reviews-pr 123`；不指定时该字段保持 unknown，工具不会遍历所有 PR。
分页或条目达到上限时报告会标记为 partial，不代表完整数据。
如需仓库默认分支、可见性和归档状态等有限元数据，可额外传入 `--include-repository`；该请求只保留标量字段。

只有额外传入 `--allow-environment-token` 才会读取 `GITHUB_TOKEN`；命令只执行 GET，不执行 GitHub 写操作。

## 隐私与安全边界

- 默认数据留在本地；可在 `continuity.json` 中启用 `privacy.anonymize_people` 和 `privacy.anonymize_repository`。前者匿名化贡献者/CODEOWNERS，后者把仓库名替换为稳定短摘要、把本地路径替换为 `<local-repository>`；依赖名仍可能含私有信息，分享前请人工审查。
- 报告中的结论必须结合输入证据、假设和规则版本阅读。
- 社区场景是受限 JSON 数据，只允许内置/声明式契约，不接受可执行字段。
- 不要把个人贡献者分数公开排名，也不要把缺失权限或缺失 API 数据当作安全。

完整边界见 [架构说明](ARCHITECTURE.md)、[GitHub 集成](GITHUB_INTEGRATION.md)、[场景注册表](SCENARIO_REGISTRY.md) 和 [发布清单](RELEASE_CHECKLIST.md)。
