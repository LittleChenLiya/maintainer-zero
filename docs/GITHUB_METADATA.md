# GitHub 元数据快照（M3 首个增量）

`maintainer_zero.github_metadata` 是一个离线校验层。它不发起网络请求，不读取
`GITHUB_TOKEN`，也不创建 Issue、评论或修改权限。经过用户审阅的只读客户端可以把
GitHub API 响应整理成 JSON，再交给 `load_metadata()` / `summarize_metadata()`。

最小载荷：

```json
{
  "schema_version": 1,
  "permissions": {
    "issues": true,
    "pull_requests": false
  },
  "data": {
    "issues": [{"number": 123}]
  }
}
```

权限为 false、权限字段缺失或数据数组缺失时，摘要将该字段标为 `null` 并列入
`unknown`。这表示“当前不可观测”，不是“没有问题”。载荷数组有 5000 项上限，
未来网络适配器仍必须自行实现超时、分页和令牌隔离。

该层是 M3 的边界契约，不代表已经完成 GitHub API 客户端。
*** Update File: D:\maintainer-zero\docs\PROJECT_GOALS.md
@@
 - [x] 生成只读恢复 Runbook、CODEOWNERS / Issue 草稿和 SARIF
+ [x] 增加离线 GitHub 元数据快照校验与权限降级摘要
