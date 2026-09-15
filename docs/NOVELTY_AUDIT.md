# 新颖性边界与持续审计

## 当前结论

针对 `maintainer succession simulator`、`open source continuity simulator`、`repository emergency drill`、`bus factor simulation` 等方向的公开检索，未发现将维护者离开、依赖撤包、CI 失效做成事件驱动时间线模拟器，并生成恢复工件的成熟开源实现。

这不是“全世界没人做过”的证明。项目对外使用以下准确表述：

> 目前未发现同一组合的成熟开源实现。

这只是截至 2026-09-11 的检索快照，不构成专利、学术优先权或“无人做过”的证明。
项目名称、README 和发布说明均不得把它表述成绝对首创。

## 2026-09-11 检索记录

使用 GitHub Repository Search API（未使用认证 token，User-Agent 为本项目审计客户端）
查询以下短语：`maintainer succession simulator`（0 个结果）、`open source continuity
simulator`（0 个结果）、`repository emergency drill`（1 个结果）、`bus factor
simulation`（4 个结果）。唯一命中 `raj-tyagi/fire-drill-assistant` 是建筑火灾疏散
路径系统（Dijkstra/C++），不分析 Git 仓库连续性；其余 `bus factor simulation`
结果也不是本项目目标领域。

检索边界：只检索 GitHub repository metadata，没有系统检索代码片段、私有仓库、
非 GitHub forge、npm/PyPI、论文或商业产品；搜索结果会随时间变化，下一次发布前必须
重新记录查询、结果数量、URL 和功能重叠。

## 相邻类别

- Bus-factor 工具：静态统计贡献集中度。
- Repository digital twin：架构、依赖和风险画像。
- 代码考古工具：理解遗留代码和历史。
- Dependabot / Snyk：依赖升级与漏洞发现。

相邻项目不等于竞争或替代品；审计只比较可验证能力，不把名称相似当成功能重叠。

Maintainer-Zero 的独立组合是：**事故剧本 → 时间线模拟 → 连续性评分 → 可执行恢复工件**。

## 防止新颖性漂移

每个版本发布前重新检索 GitHub、npm 和 PyPI，更新本文件：

1. 记录名称、URL、首次发现日期和功能重叠。
2. 对“静态分析”与“动态演练”保持明确边界。
3. 如果出现功能高度重叠的项目，优先通过互操作、引用和差异化场景解决，而不是夸大原创性。
