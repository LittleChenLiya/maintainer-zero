# Maintainer-Zero

![status](https://img.shields.io/badge/status-alpha-orange)

**Chaos engineering drills for open-source project continuity.**

> If your core maintainer disappeared for 90 days, could the project still ship a security fix?

Maintainer-Zero turns that question into a repeatable, explainable drill. It reads a local Git repository and simulates three incidents: a core maintainer becoming unavailable, a package dependency being yanked, and CI/release infrastructure going offline. It produces a score, assumptions, an incident timeline, and concrete recovery actions.

This is an early MVP. Results are heuristics, not a security certification. It does not upload repository content or call GitHub APIs.

The first M3 metadata boundary is offline-only: `maintainer_zero.github_metadata` validates
an already-reviewed JSON snapshot and preserves missing permissions as `unknown`. It does
not fetch GitHub, read tokens, or write external systems. See [GitHub metadata](docs/GITHUB_METADATA.md).

## Quick start

```powershell
cd D:\maintainer-zero
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
maintainer-zero simulate . --scenario all --output .continuity
# CI gate: fail if any scenario scores below 70
maintainer-zero simulate . --scenario all --fail-under 70
# Compare with a previous report; regression returns exit code 1
maintainer-zero simulate . --baseline .continuity/continuity.json
# Optionally attach a reviewed, read-only metadata snapshot (no network access)
maintainer-zero simulate . --github-metadata github-metadata.json
```

Open `.continuity/report.md` or `.continuity/report.html`. To create a starter config in another repository:

```bash
maintainer-zero init /path/to/repository
maintainer-zero simulate /path/to/repository --scenario maintainer-zero --days 90
```

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

## GitHub Action

This repository includes a self-analysis workflow in `.github/workflows/continuity.yml`, which runs the drill and publishes a job summary and artifact. It is not yet a reusable Marketplace Action: copying the workflow alone into another repository will not install the tool. See [GitHub integration](docs/GITHUB_INTEGRATION.md) for the current boundary. PR comments and a hosted badge endpoint are planned.

## Roadmap

See [the long-term execution plan](docs/LONG_TERM_GOAL.md) for milestones and acceptance criteria.

- GitHub API adapter for Issues, reviews, permissions, and release metadata
- CODEOWNERS and recovery-plan patch suggestions
- monthly scheduled drills and score history
- PR score regression gate with `--fail-under`
- scenario registry (`npm-token-expired`, `pypi-owner-unavailable`, `security-flood`)
- privacy-preserving public benchmark

## Why this is a distinct category

Bus-factor dashboards statically count contributors; dependency scanners find package vulnerabilities; digital-twin tools map architecture. Maintainer-Zero simulates the *sequence of consequences after an operational failure* and turns the result into a recovery plan. Public searches found adjacent tools, but no mature open-source implementation combining those capabilities.

## Contributing

Add a scenario with explicit assumptions, a deterministic test, and a short explanation of how its score is calculated. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT
