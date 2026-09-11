# GitHub 元数据快照（M3 首个增量）

`maintainer_zero.github_metadata` 是一个离线校验层。它不发起网络请求，不读取
`GITHUB_TOKEN`，也不创建 Issue、评论或修改权限。经过用户审阅的只读客户端可以把
GitHub API 响应整理成 JSON，再交给 `load_metadata()` / `summarize_metadata()`。
CLI 可以通过 `simulate --github-metadata PATH` 读取这个快照；报告只保存摘要和
unknown 状态，不复制原始记录。该参数不会触发网络请求。

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

该层是 M3 的边界契约；`collect-github` 只把这个边界接到显式授权的只读 HTTPS GET，
不提供 GitHub 写客户端。

## 显式 CLI 采集

可以用 `collect-github` 生成本地快照，但网络默认关闭：

```powershell
maintainer-zero collect-github octo-org/example --allow-network --output github-metadata.json
```

该命令只请求 issues、pull requests 和 releases 的 HTTPS GET 接口；reviews 在没有
具体 PR 编号时保持 unknown。只有同时传入 `--allow-environment-token` 才会读取
`GITHUB_TOKEN`，命令没有 token 参数，也不会把 token 写入输出。失败的权限、限流、
超时或传输错误会保留为不可用/unknown，而不是被解释为安全。

## 注入式只读客户端

`maintainer_zero.github_client.ReadOnlyGitHubClient` 提供了一个不绑定 HTTP 库的
传输边界。调用方注入 `fetch(path, params, timeout)`，自行决定认证、代理和网络
策略；客户端只允许四类 GET 资源路径，并将结果整理成同一快照格式。

客户端具备以下可测试约束：

- 每个资源最多读取有限页数，支持 GitHub `Link: rel="next"` 分页提示；
- 限制单页大小、单响应字节数和总记录数；
- 401/403/404/429、非 200、超时/传输异常、非法 JSON 均降级为不可用并保留原因；
- 不接收或写入 token，不执行任何 POST、PATCH、DELETE，不创建 Issue 或评论。

这是真实网络适配器的安全内核，而不是默认联网功能。项目仍不提供内置 HTTP
认证客户端；启用网络前，调用方必须提供经过审阅的 GET-only transport，并自行
处理凭证隔离、速率等待和组织策略。

## 标准库 HTTP transport（显式 opt-in）

`maintainer_zero.github_http.GitHubHTTPTransport` 提供一个最小的 stdlib GET transport：
只接受白名单资源路径、强制 HTTPS、限制响应体大小、支持调用方注入 opener，且构造
对象不会联网。环境变量 `GITHUB_TOKEN` 只有在 `from_environment(allow_environment=True)`
时才读取；默认不读取 token。HTTP 429/403 的响应和 `Retry-After` 头会交给上层只读
客户端处理，transport 不自动重试或隐藏等待。测试使用 fake opener，项目不在 CI 中访问
真实 GitHub。
