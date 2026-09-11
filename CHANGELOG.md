# Changelog

本文件记录尚未发布的本地开发版本；项目当前没有公开远程仓库或已发布包。

## Unreleased

- 增加确定性连续性模拟器、维护者/依赖/CI 三类核心演练。
- 增加版本化报告、稳定 Finding ID、基线回归门禁和本地趋势历史。
- 增加离线 GitHub 元数据快照、受控只读 GET transport 与默认禁用的 PR 评论草稿边界。
- 增加 10 个 data-only 社区场景样例和 3 个事故前/改进后 Demo。
- 增加 `maintainer-zero demo` 文本/JSON 输出、回归门禁，以及包内默认 Demo fixture。
- 加固 Demo 和场景输入校验：大小、字段、类型、计数、控制字符和禁止执行字段均有边界。
- 完成本地 wheel/sdist 构建和隔离安装烟测；CI 矩阵仍需由 GitHub Actions 实际运行确认。

## 发布说明

正式版本发布前应重新执行 [新颖性审计](docs/NOVELTY_AUDIT.md)、[发布清单](docs/RELEASE_CHECKLIST.md) 和跨平台 CI，并明确记录尚未验证的外部集成。
