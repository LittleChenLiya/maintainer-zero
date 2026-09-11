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

注入的 publisher 必须接收关键字参数 `body` 和 `idempotency_key`，并返回非空的评论
标识字符串。模块会校验草稿大小和 SHA-256 格式的幂等键；不会自动重试。
publisher 抛出 `PermissionError` 时会转换成不含底层消息的权限错误，其他异常也会
被转换成通用失败，避免把 token、响应正文或远端细节传播到报告。调用方仍需负责
最小权限（通常为 `pull-requests: write`）、按幂等键查找或更新评论、限速等待和
重试策略。
