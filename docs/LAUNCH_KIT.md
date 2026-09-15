# Maintainer-Zero Launch Kit

这份文档是项目的对外发布素材。所有文案都应保留项目当前边界：这是 alpha 版、本地离线优先的启发式连续性演练工具，不是安全认证，也不等于真实 hosted runner 灾难恢复证明。

## 一句话定位

如果核心维护者消失 90 天，你的开源项目还能修复安全问题并发布吗？Maintainer-Zero 把这个问题变成一次可重复、可解释、默认离线的灾难演练。

## 官方链接

- Repository: <https://github.com/LittleChenLiya/maintainer-zero>
- Show-and-tell discussion: <https://github.com/LittleChenLiya/maintainer-zero/discussions/5>
- 快速开始: [README.md](../README.md#quick-start)
- 长期目标: [LONG_TERM_GOAL.md](LONG_TERM_GOAL.md)
- 新颖性边界: [NOVELTY_AUDIT.md](NOVELTY_AUDIT.md)
- 贡献指南: [CONTRIBUTING.md](../CONTRIBUTING.md)

## GitHub 项目简介（Description）

Chaos engineering drills for open-source project continuity: simulate maintainer absence, yanked dependencies, and CI/release outages, then generate explainable scores and recovery drafts.

## 英文 GitHub Launch Post

~~~text
What happens to an open-source project when its core maintainer disappears for 90 days?

Maintainer-Zero turns that uncomfortable question into a repeatable local chaos drill.

It simulates:
- core maintainer unavailability
- a critical dependency being yanked
- CI/release infrastructure going offline

Then it produces an explainable score, event timeline, assumptions, regression gates, and recovery drafts (runbook, CODEOWNERS, issue drafts, SARIF).

The project is offline by default and never writes to GitHub. Optional provider metadata is explicit, read-only, bounded, and injected as a reviewed snapshot.

Try it in 30 seconds:

    git clone https://github.com/LittleChenLiya/maintainer-zero.git
    cd maintainer-zero
    python -m pip install -e .
    maintainer-zero demo

This is an alpha MVP, not a security certification or proof of real hosted-runner disaster recovery. Feedback and scenario contributions are welcome.

https://github.com/LittleChenLiya/maintainer-zero
~~~

## X / Twitter 短帖

~~~text
Maintainer-Zero: local chaos drills for maintainer absence, yanked deps, and CI outages. Heuristic score + recovery drafts.

alpha; offline-by-default; No automatic GitHub writes. This is no security certification and no real recovery proof.

Try: https://github.com/LittleChenLiya/maintainer-zero
~~~

## 中文技术社区短帖（掘金 / V2EX）

~~~text
开源项目最容易被忽略的故障，不是代码崩溃，而是“没人能接手”。

我做了 Maintainer-Zero：一个面向开源项目连续性的灾难演练工具。它在本地模拟核心维护者失联、依赖撤包、CI/发布链路中断三类事故，输出事件时间线、连续性评分、基线回归结果，以及 runbook、CODEOWNERS 和 Issue 草稿。

特点：默认离线、不写 GitHub；元数据采集必须显式授权，只读且有边界；报告可导出 JSON/Markdown/HTML，并带 manifest 和离线完整性凭证。

30 秒体验：
python -m pip install -e .
maintainer-zero demo

项目仍是 alpha MVP，评分是启发式结果，不是安全认证，也不代表真实 hosted runner 的灾难恢复证明。欢迎提交真实项目结构下的场景和反例。

https://github.com/LittleChenLiya/maintainer-zero
~~~

## 30 秒现场演示

复制到真实仓库的 consumer workflow 会在任意分支 push、pull request、月度定时或手动触发时运行，不假设对方默认分支一定叫 `main`；首份报告可以自然演变为持续的连续性检查。复制后请按 [首次接入检查清单](CONSUMER_WORKFLOW_CHECKLIST.md) 做一次人工复核。

在已安装 Python 3.10+ 的环境中：

~~~powershell
git clone https://github.com/LittleChenLiya/maintainer-zero.git
cd maintainer-zero
python -m pip install -e .
maintainer-zero demo --format json --output .continuity/demo.json
Get-Content .continuity/demo.json
~~~

如果要对任意本地 Git 仓库演练：

~~~powershell
maintainer-zero simulate C:\\path\\to\\repo --scenario all --output .continuity
start .continuity\\report.html
~~~

演示不联网、不读取 token、不执行 fixture 中的命令，也不会修改被分析的仓库。

## GitHub Discussions 首帖模板

标题：Show us your project’s maintainer-zero score

~~~text
大家好，欢迎分享你用 Maintainer-Zero 做连续性演练后的结果。

请尽量只分享脱敏后的摘要，不要上传私有仓库源码、token、完整 contributor 名单或内部依赖细节。可以贴：

1. 使用的场景（maintainer-zero / dependency-yanked / ci-release-outage）
2. 演练发现的一个最重要缺口
3. 你准备采取的恢复动作
4. 工具版本和运行平台

Maintainer-Zero 当前是 alpha MVP，结果是启发式评估，不是安全认证。欢迎报告误报、漏报和新的 data-only 场景。
~~~

## 发布前检查

- [ ] 链接指向公开仓库，README 的快速开始命令可运行。
- [ ] 文案使用 “currently no mature implementation found” 一类谨慎表述，不使用“全球首个”或“必然爆火”。
- [ ] 先运行 python -m pytest -q 和 maintainer-zero demo。
- [ ] 分享报告前确认匿名化配置开启，并检查依赖名称和 finding 是否包含敏感信息。
- [ ] 不在帖子、Issue、截图或 artifact 中放入 token、私有 URL 或未经审阅的仓库元数据。
- [ ] 收集反馈时优先记录可复现的场景、输入快照和期望结果。

## 适合寻找的第一批用户

1. 有多个维护者、但没有明确接班人的中小型开源项目。
2. 需要做供应链风险演练的 DevOps / platform 团队。
3. 维护 Python、Node.js 等依赖发布链路的项目。
4. 想把 CODEOWNERS、发布 runbook 和安全响应流程变成可测试资产的基金会或社区。

## 反馈入口

优先使用 GitHub Issues 提交 bug，使用 Discussions 分享演练经验；新的场景请遵循 CONTRIBUTING.md 的 data-only 和可复现要求。
