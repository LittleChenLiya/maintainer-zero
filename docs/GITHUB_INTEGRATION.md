# GitHub integration

Maintainer-Zero is local-first. The analyzer does not call a GitHub API or upload source files. The shipped workflow runs on a GitHub-hosted runner and explicitly publishes the generated report to a job summary and artifact. Set `privacy.anonymize_people` and `privacy.anonymize_repository` to `true` before sharing reports outside the repository; the starter config enables both.

## Included workflows

- ci.yml tests Python 3.10 and 3.12 on Ubuntu and Windows, then runs a CLI smoke test.
- continuity.yml runs the three drills on pushes, pull requests, a monthly schedule, or manual dispatch on both Ubuntu and Windows runners. Each matrix leg publishes the report to its Job Summary and uploads a separately named 14-day artifact. Summary and artifact steps use `always()`, so a score/baseline gate failure still leaves the generated evidence available for review; if setup fails before any report exists, the summary records that fact and artifact upload warns rather than masking the original failure.
- `action.yml` is a reusable composite Action. It installs the pinned action checkout with no dependencies and runs the same local CLI against `github.workspace`; inputs are passed through environment variables and shell arrays rather than interpolated into commands.

Both workflows use contents: read, disable checkout credential persistence, cap execution time, and cancel superseded runs. They do not use `pull_request_target`, external write permissions, or an unreviewed network client, so fork pull requests stay within the local-analysis boundary.

## Optional API adapter (v0.2 boundary)

The current `maintainer_zero.github_metadata` module validates offline snapshots produced by a separately reviewed client. The optional `github_http` transport is an explicit, GET-only stdlib boundary; it is never enabled by default and does not hide rate-limit waits. It preserves missing permissions as `unknown`; callers remain responsible for least-privilege credentials and policy:

For a real repository, `maintainer-zero collect-github OWNER/REPOSITORY --allow-network`
connects that boundary to a local snapshot. Network access is opt-in, and reading
`GITHUB_TOKEN` requires the additional `--allow-environment-token` flag. The command never
performs GitHub writes; review the resulting JSON before passing it to `simulate`.

| Capability | Required permission | Write access |
| --- | --- | --- |
| Issues / pull requests / reviews | contents: read, issues: read, pull-requests: read | None |
| Release and tag metadata | contents: read | None |
| PR comment (opt-in) | pull-requests: write | Comment only |

The adapter should accept GITHUB_TOKEN only through explicit opt-in, redact repository names and people in exported reports when configured, and fail closed when a permission is missing. `anonymize_repository` replaces the basename and absolute path with a stable short digest and `<local-repository>`; it does not send the original identity anywhere. It must never print tokens or upload raw prompts, repository files, or unredacted report payloads.
The checked-in continuity workflow uploads the JSON, Markdown, HTML, SARIF, Runbook, CODEOWNERS draft, and Issue draft artifacts together on each OS; these are reviewable suggestions and are not written back to the repository or GitHub.

## PR 评论草稿边界

`maintainer_zero.pr_comment` 只生成本地评论草稿和稳定幂等键，默认拒绝发布。
只有调用方显式传入 `enabled=True` 以及自有 publisher，才会把正文交给外部适配器；
项目本身不联网、不读取 token，也不提供 GitHub 写客户端。详见 [PR 评论边界](PR_COMMENTS.md)。

## Reusable composite Action (local contract)

仓库可以在审阅后引用根目录的 `action.yml` 作为 composite Action。它只安装当前 checkout 中的包并运行本地 `simulate`；输入通过环境变量转成参数列表，不拼接 shell 命令。Action 不读取 token、不启用网络、不写 GitHub，成功后输出 `report-directory`、`report-json`、`report-markdown`、`report-html`、`recovery-directory` 和 `artifact-manifest` 的绝对路径。调用方仍负责 checkout、Python 环境和最小权限：

```yaml
permissions:
  contents: read
steps:
  - uses: actions/checkout@v4
    with:
      persist-credentials: false
  - uses: ./
    with:
      scenario: all
      fail-under: '70'
```

当前仓库尚未发布到 Marketplace；Action 对 Unix runner 使用 `bash`，对 Windows runner 使用 `pwsh`，本地契约测试验证两种 shell 分支和输入边界，但不等同于真实远程 runner 结果。

## Setup for a repository

The repository now includes a reusable composite Action at its root. After a reviewed release is tagged, a consuming repository can call it from a pinned ref after checkout. On success it exposes `artifact-manifest` and `integrity-credential`, absolute paths to local integrity artifacts; verify them offline with `maintainer-zero verify-manifest` and `maintainer-zero verify-credential` before sharing artifacts:

```yaml
- uses: actions/checkout@v4
  with:
    persist-credentials: false
- uses: OWNER/maintainer-zero@<reviewed-tag>
  with:
    scenario: all
    output: .continuity
    fail-under: "70"
```

The Action remains local-first: it installs only the action checkout, does not contact GitHub, and writes only to the configured output directory. The consuming workflow should pin a reviewed tag or commit, keep `contents: read`, and use `pull_request` rather than `pull_request_target` for untrusted forks. The checked-in `continuity.yml` exercises the same Action locally.

For a private repository, review the generated artifact before sharing it outside the organization. Add verified GitHub handles to .github/CODEOWNERS before enabling required reviews; no owner is assigned by default.
