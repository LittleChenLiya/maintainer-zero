# GitHub 元数据快照（M3 首个增量）

`maintainer_zero.github_metadata` 是一个离线校验层。它不发起网络请求，不读取
`GITHUB_TOKEN`，也不创建 Issue、评论或修改权限。经过用户审阅的只读客户端可以把
GitHub API 响应整理成 JSON，再交给 `load_metadata()` / `summarize_metadata()`。
CLI 可以通过 `simulate --github-metadata PATH` 读取这个快照；报告只保存摘要和
unknown 状态，不复制原始记录。该参数不会触发网络请求。

## 本地缓存契约

如果集成方需要重复使用采集结果，可以把已校验快照包装为本地缓存：

```python
from datetime import datetime, timezone
from maintainer_zero.github_cache import save_metadata_cache, load_metadata_cache

save_metadata_cache(
    "github-cache.json", payload, source="github-api", ttl_seconds=86400,
    fetched_at=datetime.now(timezone.utc),
)
fresh = load_metadata_cache("github-cache.json")
```

缓存只增加 `cache` 元数据（来源、抓取时间、过期时间和 TTL），不改变原始
快照的 schema。TTL 必须在 1 秒到 30 天之间，时间戳必须带时区，过期时间必须
与抓取时间和 TTL 精确一致；文件大小继续受 10 MB 上限约束，并通过临时文件
替换写入。`cache_status()` 会返回 `missing`、`invalid`、`fresh` 或 `stale`。
过期缓存默认被 `load_metadata_cache()` 拒绝，只有离线审阅确实需要旧数据时才
显式传入 `allow_stale=True`。该模块不会自动刷新、联网、读取 token 或把 stale
计数解释成当前事实。

`simulate --github-metadata` 会自动识别带 `cache` envelope 的快照，并把缓存来源、
抓取时间、过期时间和 `fresh`/`stale` 状态写入报告摘要。过期缓存默认让演练以
输入错误退出；仅在明确知道自己正在进行离线复盘时传入
`--allow-stale-github-metadata`。这个开关不会刷新缓存，也不会把旧数据标记为当前事实。

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

每个响应体默认最多读取 1,000,000 字节；如需在受限网络环境中进一步缩小
边界，可以显式传入 `--max-response-bytes N`（`1 <= N <= 1,000,000`）：

```powershell
maintainer-zero collect-github octo-org/example --allow-network `
  --max-response-bytes 262144 --output github-metadata.json
```

这个参数同时约束 HTTP transport 和注入式只读客户端；它只能收紧默认上限，
不能借助命令行把响应大小上限提高。超过上限的资源会降级为不可用并保留
`response_too_large` 原因，不会把截断内容解析成完整事实。

该命令默认只请求 issues、pull requests 和 releases 的 HTTPS GET 接口；仓库可见性、归档状态和默认分支等
repository descriptor 只有传入 `--include-repository` 才会请求。reviews 在没有
具体 PR 编号时保持 unknown。若要采集单个 PR 的 reviews，必须额外传入例如
`--reviews-pr 123`，避免一次性为所有 PR 扩大请求量。只有同时传入 `--allow-environment-token` 才会读取
`GITHUB_TOKEN`，命令没有 token 参数，也不会把 token 写入输出。失败的权限、限流、
超时或传输错误会保留为不可用/unknown，而不是被解释为安全。达到页数/条目上限时，
快照会在摘要中标记 `partial`，报告中的计数不应被解释为完整列表。
快照文件通过同目录临时文件和原子替换写入；如果写入失败，已有快照不会被截断。`--output` 与 `--cache-output` 必须指向不同文件。

限流响应只会保留两个经过边界校验的调度提示：`retry_after_seconds`（最多 24 小时）
和 `rate_limit_reset_epoch`（Unix 时间戳）。它们帮助调用方安排下一次运行；工具不会
自动等待、重试或把任意响应头复制到快照，无法解析或超出范围的值会被丢弃。
这些字段会随 `collection` 状态进入机器可读演练报告；Markdown 报告仍只展示未知和部分采集提示。

响应体上限默认是 1,000,000 字节。需要更严格的网络边界时，可以显式传入
--max-response-bytes N（范围为 1 到 1,000,000）；该值同时约束 HTTP transport
和注入式客户端，不能通过 CLI 放宽全局上限。无此参数时保持默认上限。

## 注入式只读客户端

`maintainer_zero.github_client.ReadOnlyGitHubClient` 提供了一个不绑定 HTTP 库的
传输边界。调用方注入 `fetch(path, params, timeout)`，自行决定认证、代理和网络
策略；客户端只允许白名单 GET 资源路径，并将结果整理成同一快照格式。

客户端具备以下可测试约束：

- 每个资源最多读取有限页数，支持 GitHub `Link: rel="next"` 分页提示；
- 限制单页大小、单响应字节数和总记录数；
- 401/403/404/429、非 200、超时/传输异常、非法 JSON 均降级为不可用并保留原因；
- repository descriptor 只保留默认分支、可见性、归档和计数等标量字段，不复制 owner、URL 或原始仓库对象；
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
