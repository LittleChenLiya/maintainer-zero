# GitHub integration

Maintainer-Zero is local-first. The shipped workflow runs against the checkout and does not need a GitHub token or network access to inspect repository content. This keeps private code and maintainer identities out of the service boundary.

## Included workflows

- ci.yml tests Python 3.10 and 3.12 on Ubuntu and Windows, then runs a CLI smoke test.
- continuity.yml runs the three drills on pushes, pull requests, a monthly schedule, or manual dispatch. The report is appended to the Actions job summary and uploaded as a 14-day artifact.

Both workflows use contents: read, disable checkout credential persistence, cap execution time, and cancel superseded runs.

## Optional API adapter (v0.2)

The planned adapter may read issue, review, permission, and release metadata to improve estimates. It must remain opt-in and follow least privilege:

| Capability | Required permission | Write access |
| --- | --- | --- |
| Issues / pull requests / reviews | contents: read, issues: read, pull-requests: read | None |
| Release and tag metadata | contents: read | None |
| PR comment (opt-in) | pull-requests: write | Comment only |

The adapter should accept GITHUB_TOKEN from the workflow environment, redact repository names and people in exported reports when configured, and fail closed when a permission is missing. It must never print tokens or upload raw prompts, repository files, or unredacted report payloads.

## Setup for a repository

Copy .github/workflows/continuity.yml into the target repository. For a private repository, review the generated artifact before sharing it outside the organization. Replace the @OWNER placeholders in .github/CODEOWNERS with real handles before enabling required reviews.

