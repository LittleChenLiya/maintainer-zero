# PR 评论边界

Maintainer-Zero 只生成本地 PR 评论草稿，不默认访问 GitHub。`build_comment_draft()`
从报告生成确定性正文和幂等键；`publish_comment()` 只有在调用方同时显式传入
`enabled=True` 和自有 publisher 时才会调用外部写入适配器。项目不读取 token、
不实现 HTTP 客户端，也不会自动评论、更新 Issue 或修改权限。
草稿会限制记录数量，并清理仓库名与场景名中的控制字符和 Markdown 反引号；它仍不是
完整的秘密扫描，发布前应审阅内容。

这使评论内容可以先在 CI artifact 或 PR diff 中审阅。真正的 GitHub publisher
必须由集成方自行实现最小权限、token 隔离、重复更新策略和失败重试，并测试
其不会把原始报告或仓库内容发送到不必要的系统。
