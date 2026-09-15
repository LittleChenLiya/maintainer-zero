# Consumer workflow 首次接入检查清单

把 [consumer-workflow.yml](../examples/consumer-workflow.yml) 复制到目标仓库的 `.github/workflows/maintainer-zero.yml` 后，第一次运行前后逐项确认：

## 复制前

- [ ] 目标仓库允许 GitHub Actions，并且 Actions 没有被组织策略禁用。
- [ ] 已审阅工作流中的 immutable `uses:` 提交；不要把它改成未经审阅的浮动分支。
- [ ] 工作流保留 `permissions: contents: read`、`persist-credentials: false` 和 `pull_request`；不要改成 `pull_request_target`。
- [ ] 确认项目允许 Ubuntu 与 Windows hosted runner；如组织不提供其中一个 runner，按组织策略调整矩阵并记录原因。

## 第一次运行

- [ ] 用 `workflow_dispatch` 手动运行一次，确认两个 OS matrix leg 都完成。
- [ ] 检查 Job Summary 中有报告；失败时先看对应 matrix leg 的错误，不要上传未验证的输出。
- [ ] 确认每个平台都通过 report、manifest 和 integrity credential 校验，并生成独立 artifact。
- [ ] 下载 artifact 做一次人工脱敏检查；依赖名称、路径和 finding 可能仍属于项目敏感信息。

## 持续运行

- [ ] 默认工作流监听所有分支的 push，因此不要求默认分支叫 `main`；如组织只允许受保护分支，可在审阅后加上明确的分支过滤。
- [ ] 确认 Pull Request 使用 `pull_request`，不要为了读取 secrets 或写回仓库改用 `pull_request_target`。
- [ ] 保留月度 schedule，至少观察一次定时运行；它用于发现维护者、依赖和 CI/发布链路随时间产生的连续性退化。
- [ ] 将真实修复动作写回项目自己的 runbook、CODEOWNERS 或 issue 流程；Maintainer-Zero 只生成本地建议，不会自动修改 GitHub。

## 边界

Maintainer-Zero 当前是 alpha、offline-first 的启发式演练工具。分数不是安全认证，也不是真实 hosted runner 灾难恢复证明；工作流不会自动执行修复或向 GitHub 写入内容。
