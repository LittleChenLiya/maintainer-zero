# 新颖性边界与持续审计

## 当前结论

针对 `maintainer succession simulator`、`open source continuity simulator`、`repository emergency drill`、`bus factor simulation` 等方向的公开检索，未发现将维护者离开、依赖撤包、CI 失效做成事件驱动时间线模拟器，并生成恢复工件的成熟开源实现。

这不是“全世界没人做过”的证明。项目对外使用以下准确表述：

> 目前未发现同一组合的成熟开源实现。

## 相邻类别

- Bus-factor 工具：静态统计贡献集中度。
- Repository digital twin：架构、依赖和风险画像。
- 代码考古工具：理解遗留代码和历史。
- Dependabot / Snyk：依赖升级与漏洞发现。

Maintainer-Zero 的独立组合是：**事故剧本 → 时间线模拟 → 连续性评分 → 可执行恢复工件**。

## 防止新颖性漂移

每个版本发布前重新检索 GitHub、npm 和 PyPI，更新本文件：

1. 记录名称、URL、首次发现日期和功能重叠。
2. 对“静态分析”与“动态演练”保持明确边界。
3. 如果出现功能高度重叠的项目，优先通过互操作、引用和差异化场景解决，而不是夸大原创性。
