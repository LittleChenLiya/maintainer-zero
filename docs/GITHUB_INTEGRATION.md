# GitHub integration

Maintainer-Zero is local-first. The analyzer does not call a GitHub API or upload source files. The shipped workflow runs on a GitHub-hosted runner and explicitly publishes the generated report to a job summary and artifact. Reports currently contain Git author names and the repository path; review this metadata before sharing it.

## Included workflows

- ci.yml tests Python 3.10 and 3.12 on Ubuntu and Windows, then runs a CLI smoke test.
- continuity.yml runs the three drills on pushes, pull requests, a monthly schedule, or manual dispatch. The report is appended to the Actions job summary and uploaded as a 14-day artifact.

Both workflows use contents: read, disable checkout credential persistence, cap execution time, and cancel superseded runs. They do not use `pull_request_target`, external write permissions, or an unreviewed network client, so fork pull requests stay within the local-analysis boundary.

## Optional API adapter (v0.2 boundary)

The current `maintainer_zero.github_metadata` module validates offline snapshots produced by a separately reviewed client. It does not fetch GitHub or read tokens. It preserves missing permissions as `unknown`; a network client remains future work and must follow least privilege:

| Capability | Required permission | Write access |
| --- | --- | --- |
| Issues / pull requests / reviews | contents: read, issues: read, pull-requests: read | None |
| Release and tag metadata | contents: read | None |
| PR comment (opt-in) | pull-requests: write | Comment only |

The adapter should accept GITHUB_TOKEN from the workflow environment, redact repository names and people in exported reports when configured, and fail closed when a permission is missing. It must never print tokens or upload raw prompts, repository files, or unredacted report payloads.

## Setup for a repository

The supplied continuity.yml is a self-analysis workflow for this project, not yet a reusable Marketplace Action. Copying it alone into an unrelated repository will not install Maintainer-Zero. Until a reusable Action is published, install the tool from a reviewed local checkout and run it against the target repository. Keep tooling separate from untrusted pull-request code and do not use pull_request_target to execute it.

For a private repository, review the generated artifact before sharing it outside the organization. Add verified GitHub handles to .github/CODEOWNERS before enabling required reviews; no owner is assigned by default.
