# Maintainer-Zero

![status](https://img.shields.io/badge/status-alpha-orange)

**Chaos engineering drills for open-source project continuity.**

> If your core maintainer disappeared for 90 days, could the project still ship a security fix?

Maintainer-Zero turns that question into a repeatable, explainable drill. It reads a local Git repository and simulates three incidents: a core maintainer becoming unavailable, a package dependency being yanked, and CI/release infrastructure going offline. It produces a score, assumptions, an incident timeline, and concrete recovery actions.

This is an early MVP. Results are heuristics, not a security certification. It is offline by default;
the optional `collect-github` command can make explicitly authorized, read-only HTTPS GET requests
and writes only a local metadata snapshot.

For shareable reports, the starter config anonymizes contributor identities and the local repository name/path; keep `privacy.anonymize_repository` enabled unless a private local report is intended.

The M3 metadata boundary validates reviewed snapshots and preserves missing permissions as
`unknown`. Network collection requires both `--allow-network` and, for environment credentials,
`--allow-environment-token`; it never writes to GitHub. See [GitHub metadata](docs/GITHUB_METADATA.md).

## Quick start

```powershell
cd D:\maintainer-zero
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
maintainer-zero --version
maintainer-zero simulate . --scenario all --output .continuity
# CI gate: fail if any scenario scores below 70
maintainer-zero simulate . --scenario all --fail-under 70
# Compare with a previous report; score regression returns exit code 1 by default
maintainer-zero simulate . --baseline .continuity/continuity.json
# Select explicit baseline gate policies in CI
maintainer-zero simulate . --baseline old.json --fail-on-score-decrease --fail-on-new-high-risk
# Optionally attach a reviewed, read-only metadata snapshot (no network access)
maintainer-zero simulate . --github-metadata github-metadata.json
# Cached snapshots are freshness-checked; stale data requires an explicit offline-review opt-in
maintainer-zero simulate . --github-metadata github-cache.json --allow-stale-github-metadata
# Explicitly collect bounded read-only metadata (network is otherwise disabled)
maintainer-zero collect-github OWNER/REPOSITORY --allow-network --output github-metadata.json
# Tighten the per-response body bound when reviewing a constrained endpoint
maintainer-zero collect-github OWNER/REPOSITORY --allow-network --max-response-bytes 262144 --output github-metadata.json
# Optional, bounded review metadata for one explicitly named pull request:
maintainer-zero collect-github OWNER/REPOSITORY --allow-network --reviews-pr 123 --output github-metadata.json
# Optional bounded repository descriptor (visibility/default branch):
maintainer-zero collect-github OWNER/REPOSITORY --allow-network --include-repository --output github-metadata.json
# Optionally wrap the reviewed collection in a bounded local cache
maintainer-zero collect-github OWNER/REPOSITORY --allow-network --output github-metadata.json --cache-output .continuity/github-cache.json --cache-ttl 86400
# Read a cache offline; expired caches fail unless explicitly allowed
maintainer-zero simulate . --github-metadata .continuity/github-cache.json --output .continuity
maintainer-zero simulate . --github-metadata .continuity/github-cache.json --allow-stale-github-metadata --output .continuity
# Keep a local, same-repository score history (no raw repository records)
maintainer-zero simulate . --history .continuity/history.json
# Validate a declarative community scenario without executing code
maintainer-zero validate-scenario examples/scenarios/dependency-yanked.json
# Print a validated, non-executable scenario contract for review
maintainer-zero describe-scenario examples/scenarios/dependency-yanked.json --format json
# Validate the complete versioned registry without executing code
maintainer-zero validate-registry maintainer_zero/scenario_registry.json
# Run the checked-in, offline before/after demo suite (no GitHub access)
maintainer-zero demo
maintainer-zero demo --format json --output .continuity/demo.json
```

Open `.continuity/report.md` or `.continuity/report.html`. To create a starter config in another repository. Report JSON, Markdown, and HTML files are written with same-directory temporary files and atomic replacement; an interrupted write does not intentionally truncate an existing artifact:

```bash
maintainer-zero init /path/to/repository
maintainer-zero simulate /path/to/repository --scenario maintainer-zero --days 90
```

The starter config enables `privacy.anonymize_people` and `privacy.anonymize_repository`, so
shareable reports do not include contributor identities, the repository basename, or the local
absolute path. The generated `continuity.json` also records a small `privacy` boundary summary
and explicitly states that repository-content upload is disabled. Dependency names and findings
can still be repository-sensitive; review artifacts before publishing them.

Three offline before/after demos are available in [examples/demos](examples/demos/continuity-demos.json);
they use data-only snapshots and never execute fixture paths or commands. See [demo guide](docs/DEMOS.md).

Each simulation also creates reviewable recovery drafts under `.continuity/recovery/`:
`runbook.md`, `CODEOWNERS.draft`, and `issue-drafts.md`. They are suggestions only;
the CLI never edits the analyzed repository, changes permissions, or submits GitHub
Issues. Use `--recovery-output PATH` to choose another output directory. See
[恢复工件说明](docs/RECOVERY_ARTIFACTS.md).

## What it inspects

- Git commit authors (via `git log`)
- `CODEOWNERS` in common locations
- dependencies in `package.json`, `requirements*.txt`
- workflow files under `.github/workflows`
- common release configuration files

## Output

```text
.continuity/
├── continuity.json   # machine-readable result
├── report.md         # reviewable report for a PR
├── report.html        # standalone local view
└── recovery/          # Runbook, CODEOWNERS, Issue drafts and SARIF
```

With `--history`, the output also includes `history-summary.json` and a path-free, human-reviewable `history-summary.md`; see
[同仓库趋势历史](docs/TREND_HISTORY.md). History is local-only and is not a
cross-project ranking.

## GitHub Action

This repository includes a self-analysis workflow in `.github/workflows/continuity.yml`, which runs the drill and publishes a job summary and artifact. The root `action.yml` is also a reusable composite Action; consumers should pin a reviewed tag or commit and keep the workflow read-only. See [GitHub integration](docs/GITHUB_INTEGRATION.md) for the setup and security boundary. PR comments are available as local drafts only; external publishing remains an explicitly injected integration.

## Roadmap

See [the long-term execution plan](docs/LONG_TERM_GOAL.md) for milestones and acceptance criteria.
中文用户可参阅 [中文使用指南](docs/GUIDE_ZH.md)；开发变更记录见 [CHANGELOG.md](CHANGELOG.md)。

- GitHub API adapter for Issues, reviews, permissions, and release metadata
- CODEOWNERS and recovery-plan patch suggestions
- monthly scheduled drills and score history
- PR score regression gate with `--fail-under`
- scenario registry (`npm-token-expired`, `pypi-owner-unavailable`, `security-flood`)
- privacy-preserving public benchmark

## Why this is a distinct category

Bus-factor dashboards statically count contributors; dependency scanners find package vulnerabilities; digital-twin tools map architecture. Maintainer-Zero simulates the *sequence of consequences after an operational failure* and turns the result into a recovery plan. Public searches found adjacent tools, but no mature open-source implementation combining those capabilities.

The checked-in scenario registry is available at maintainer_zero/scenario_registry.json. It is a versioned, data-only contract for scenario review; registry loading never executes an entrypoint or formula. See docs/SCENARIO_REGISTRY.md for contribution and safety rules.

## Contributing

Add a scenario with explicit assumptions, a deterministic test, and a short explanation of how its score is calculated. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT
