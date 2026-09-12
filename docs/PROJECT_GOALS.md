# Maintainer-Zero 项目目标

长期执行计划、里程碑和当前进度见 [LONG_TERM_GOAL.md](LONG_TERM_GOAL.md)。

## 北极星目标

让任何 GitHub 开源仓库都能在 5 分钟内回答：

> 核心维护者、关键依赖或 CI 发布链路今天失效，项目能否在可接受时间内继续修复、审查和发布？

## v0.1 完成定义

- [x] 从本地 Git 历史识别贡献者和提交集中度
- [x] 扫描 CODEOWNERS、依赖清单、工作流和发布配置
- [x] 实现 `maintainer-zero`、`dependency-yanked`、`ci-outage` 三个确定性演练
- [x] 输出可读 Markdown、独立 HTML 和机器可读 JSON
- [x] 提供 Python CLI、可编辑安装和 GitHub Action
- [x] 默认离线运行，不上传仓库内容
- [x] 为核心评分和边界情况提供自动化测试

## 设计原则

1. **可解释**：每个分数都能追溯到输入、假设和公式。
2. **不羞辱维护者**：报告项目级单点风险，不公开点名或排名个人。
3. **隐私优先**：本地优先；未来接 GitHub API 时也只请求最小权限。
4. **可操作**：每个发现必须对应一个 CODEOWNERS、Runbook、凭证或 CI 改进动作。
5. **可重复**：同一仓库、同一参数的结果应稳定，方便在 Git 中追踪趋势。

## v0.2 目标

- [x] 可选 `--fail-under` 连续性评分门禁，可用于 CI / PR
- [x] 维护者离开场景接入确定性积压模拟器
- [x] 三类核心场景共享可解释的事故积压与假设恢复指标
- [x] 版本化报告 schema、稳定 finding ID 与 `--baseline` 比较
- [x] 生成只读恢复 Runbook、CODEOWNERS / Issue 草稿和 SARIF
- [x] 增加离线 GitHub 元数据快照校验与权限降级摘要
- [x] 注入式只读 GitHub 元数据客户端边界：分页、响应限制和错误降级
- [x] CLI 接受已审阅的元数据快照并把脱敏摘要写入报告
- [x] 显式 opt-in 的 GitHub GET 采集命令已覆盖 issues、pull requests、releases，以及显式 `--include-repository` 的有限仓库描述；reviews 需指定单个 PR，分页截断会标记 `partial`；缓存、速率等待与真实写入仍由后续集成负责
- [x] 从报告生成 CODEOWNERS / Issue / Runbook 草稿（均为本地、待审阅草稿）
- [x] 维护者匿名化和稳定的组织内角色占位映射；组织身份解析仍需用户提供映射
- [x] PR 评论、分数回归门禁和 SARIF 输出；PR 评论仍只生成本地草稿，不自动写 GitHub
- [x] 每月定时演练 workflow 和同仓库历史摘要；真实远程 runner 与历史图表发布仍需外部验证

## v1.0 目标

- 社区场景注册表和版本化演练剧本
- 依赖替代路径与冷构建验证
- 签名的演练凭证和可验证报告
- 隐私保护的公开基准测试
- 支持 GitLab、Forgejo 等兼容平台

## 成功指标

- 新用户从克隆到首份报告不超过 5 分钟
- 10 个演练样例在 60 秒内完成
- 关键风险发现的人工复核 precision ≥ 0.9
- 至少 20 个真实开源仓库持续运行月度演练
- 社区贡献至少 10 个可复用事故场景

## 非目标

- 不替代 Dependabot、Snyk、OpenSSF Scorecard 或 CI 平台
- 不声称提供安全认证、法律合规结论或精确事故概率
- 不在未授权情况下写入 GitHub Issue、PR、权限或仓库文件
