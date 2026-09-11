# GitHub integration

Maintainer-Zero is local-first. The analyzer does not call a GitHub API or upload source files. The shipped workflow runs on a GitHub-hosted runner and explicitly publishes the generated report to a job summary and artifact. Reports currently contain Git author names and the repository path; review this metadata before sharing it.

## Included workflows

- ci.yml tests Python 3.10 and 3.12 on Ubuntu and Windows, then runs a CLI smoke test.
- continuity.yml runs the three drills on pushes, pull requests, a monthly schedule, or manual dispatch. The report is appended to the Actions job summary and uploaded as a 14-day artifact.

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

The adapter should accept GITHUB_TOKEN only through explicit opt-in, redact repository names and people in exported reports when configured, and fail closed when a permission is missing. It must never print tokens or upload raw prompts, repository files, or unredacted report payloads.

## PR 评论草稿边界

`maintainer_zero.pr_comment` 只生成本地评论草稿和稳定幂等键，默认拒绝发布。
只有调用方显式传入 `enabled=True` 以及自有 publisher，才会把正文交给外部适配器；
项目本身不联网、不读取 token，也不提供 GitHub 写客户端。详见 [PR 评论边界](PR_COMMENTS.md)。

## Setup for a repository

The supplied continuity.yml is a self-analysis workflow for this project, not yet a reusable Marketplace Action. Copying it alone into an unrelated repository will not install Maintainer-Zero. Until a reusable Action is published, install the tool from a reviewed local checkout and run it against the target repository. Keep tooling separate from untrusted pull-request code and do not use pull_request_target to execute it.

For a private repository, review the generated artifact before sharing it outside the organization. Add verified GitHub handles to .github/CODEOWNERS before enabling required reviews; no owner is assigned by default.
