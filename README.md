# Maintainer-Zero

![status](https://img.shields.io/badge/status-alpha-orange)
[![CI](https://github.com/LittleChenLiya/maintainer-zero/actions/workflows/ci.yml/badge.svg)](https://github.com/LittleChenLiya/maintainer-zero/actions/workflows/ci.yml)
[![OSS continuity drill](https://github.com/LittleChenLiya/maintainer-zero/actions/workflows/continuity.yml/badge.svg)](https://github.com/LittleChenLiya/maintainer-zero/actions/workflows/continuity.yml)

**Chaos engineering drills for open-source project continuity.**

> If your core maintainer disappeared for 90 days, could the project still ship a security fix?

Maintainer-Zero turns that question into a repeatable, explainable drill. It reads a local Git repository and simulates three incidents: a core maintainer becoming unavailable, a package dependency being yanked, and CI/release infrastructure going offline. It produces a score, assumptions, an incident timeline, and concrete recovery actions.

This is an early MVP. Results are heuristics, not a security certification. It is offline by default;
the optional `collect-github` command can make explicitly authorized, read-only HTTPS GET requests
and writes only a local metadata snapshot.

For shareable reports, the starter config anonymizes contributor identities and the local repository name/path; keep `privacy.anonymize_repository` enabled unless a private local report is intended.

[Quick start](#quick-start) · [中文指南](docs/GUIDE_ZH.md) · [Demo guide](docs/DEMOS.md) · [Releases](https://github.com/LittleChenLiya/maintainer-zero/releases) · [Show and tell](https://github.com/LittleChenLiya/maintainer-zero/discussions/5) · [Share feedback](https://github.com/LittleChenLiya/maintainer-zero/discussions/4)

## Quick start

With Python 3.10+ and Git installed, run directly from a clone on Windows, macOS, or Linux.
The CLI has no runtime package dependencies and the demo needs no token or network access
after cloning:

```sh
git clone https://github.com/LittleChenLiya/maintainer-zero.git
cd maintainer-zero
python -m maintainer_zero demo --fail-on-regression
python -m maintainer_zero simulate . --scenario all --output .continuity
```

Use `python3` if that is your Python 3 executable. The demo prints:

```text
Demo suite: 3 data-only demo(s)
  maintainer-handoff (maintainer-zero): 15 -> 85 (+70, improved)
  dependency-cold-build (dependency-yanked): 60 -> 84 (+24, improved)
  ci-release-fallback (ci-outage): 60 -> 95 (+35, improved)
```

These are synthetic before/after snapshots, not measured recovery performance. The demo
does not execute builds, yank packages, or disable CI. Scores are heuristics, not a
security certification or proof of real disaster recovery.

Open `.continuity/report.html` for the local report and `.continuity/recovery/runbook.md`
for recovery suggestions. To inspect your own local Git checkout, replace the `.` after
`simulate` with its path. Review reports before sharing; dependency names and findings
may still be sensitive.

## Optional metadata

The M3 metadata boundary validates reviewed snapshots and preserves missing permissions as
`unknown`. Network collection requires both `--allow-network` and, for environment credentials,
`--allow-environment-token`; it never writes to GitHub. See [GitHub metadata](docs/GITHUB_METADATA.md).
Provider-neutral adapters can use the injected GitLab/Forgejo client and canonical mapping, but
these APIs perform no network I/O by themselves and do not load tokens or perform write operations.
An optional `ProviderHTTPTransport` supplies the same bounded HTTPS GET boundary for GitLab and
Forgejo; it requires an explicit API base and never performs writes or implicit token loading.

The collect-provider command exposes that boundary for GitLab and Forgejo. Network access,
environment-token loading, and the API base are all explicit:

```powershell
maintainer-zero collect-provider gitlab 42 --api-base https://gitlab.example --allow-network --output gitlab-metadata.json
maintainer-zero collect-provider forgejo acme/demo --api-base https://forgejo.example --allow-network --include-repository --output forgejo-metadata.json
```

The command only issues bounded HTTPS GET requests to provider-fixed paths. GITLAB_TOKEN or
FORGEJO_TOKEN is read only with --allow-environment-token; no token is written to the snapshot,
and failed or partial resources remain explicitly unavailable/unknown.

## Installed CLI and advanced options

To use the `maintainer-zero` command, install from the checkout in an activated virtual
environment. Create one with `python -m venv .venv`; activate with
`.venv\Scripts\Activate.ps1` on Windows or `source .venv/bin/activate` on macOS/Linux.

```powershell
python -m pip install -e .
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
# Collect GitLab/Forgejo through the explicit HTTPS adapter (network remains opt-in)
maintainer-zero collect-provider gitlab 42 --api-base https://gitlab.example --allow-network --output gitlab-metadata.json
maintainer-zero collect-provider forgejo acme/demo --api-base https://forgejo.example --allow-network --reviews-pr 7 --output forgejo-metadata.json
# Read a cache offline; expired caches fail unless explicitly allowed
maintainer-zero simulate . --github-metadata .continuity/github-cache.json --output .continuity
maintainer-zero simulate . --github-metadata .continuity/github-cache.json --allow-stale-github-metadata --output .continuity
# Keep a local, same-repository score history (no raw repository records)
maintainer-zero simulate . --history .continuity/history.json
# Attach a reviewed, data-only dependency fallback/cold-build plan (never executes it)
maintainer-zero simulate . --fallback-plan fallback.json
# Validate the plan alone before attaching it to a report (still never executes it)
maintainer-zero validate-fallback-plan fallback.json --format json
# Export a privacy-preserving summary for an explicitly reviewed benchmark
maintainer-zero export-benchmark .continuity/continuity.json --output benchmark.json
# Validate a benchmark summary before sharing it (offline, data-only)
maintainer-zero validate-benchmark benchmark.json --format json
# Validate a continuity report before sharing or using it as a baseline (offline, data-only)
maintainer-zero validate-report .continuity/continuity.json --format json
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

Every simulation also writes `.continuity/artifact-manifest.json`, a local SHA-256 and size
manifest for artifacts that were actually produced (including optional history and baseline
sidecars). Verify it offline with `maintainer-zero verify-manifest .continuity/artifact-manifest.json`.
The manifest uses relative paths, rejects links and special files, and excludes its own hash. It
proves local artifact integrity only; it is not a digital signature and does not prove provenance.
No artifact is uploaded by this command.

Simulations also write `.continuity/continuity-credential.json`, an offline-verifiable envelope
that binds `continuity.json` to the manifest and records a deterministic SHA-256 content digest.
Use `maintainer-zero verify-credential .continuity/continuity-credential.json` to check it,
or create one for existing files with `maintainer-zero create-credential REPORT MANIFEST`.
This is explicitly not a digital signature and does not establish source, identity, or authority.

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

A copy-paste consumer workflow is available at examples/consumer-workflow.yml. It runs on pushes to any branch, pull requests, a monthly schedule, or manual dispatch; this avoids assuming that an adopting repository calls its default branch `main`. It pins the reviewed v0.2.2 alpha commit, runs on Ubuntu and Windows, exports the Action code path for follow-up validation, and verifies report integrity before upload. See the [first-run checklist](docs/CONSUMER_WORKFLOW_CHECKLIST.md) after copying it.
This repository includes a self-analysis workflow in `.github/workflows/continuity.yml`, which runs the drill and publishes a job summary and artifact. The root `action.yml` is also a reusable composite Action; consumers should pin a reviewed tag or commit and keep the workflow read-only. See [GitHub integration](docs/GITHUB_INTEGRATION.md) for the setup and security boundary. PR comments are available as local drafts only; external publishing remains an explicitly injected integration.

### First run after copying the workflow

Copy `examples/consumer-workflow.yml` to `.github/workflows/maintainer-zero.yml`, commit it, and open the repository's **Actions** tab. Use **Run workflow** for a controlled first run when the file is present on the default branch; otherwise make a small push or open a pull request to exercise the workflow. A successful run has one Ubuntu and one Windows matrix leg, a report in each Job Summary, and one 14-day artifact per platform. The artifact upload is intentionally gated on report, manifest, and integrity-credential validation.

If the first run does not look like that, start with this short diagnostic table:

| Symptom | Check first | Safe next action |
| --- | --- | --- |
| The workflow is not listed or **Run workflow** is missing | The file is under `.github/workflows/` and Actions are enabled; manual dispatch is shown only when the workflow exists on the default branch | Commit the file to the default branch, or trigger a push/PR and inspect the workflow file validation |
| `LittleChenLiya/maintainer-zero@…` cannot be resolved | The pinned commit is reachable and exactly 40 hexadecimal characters; do not replace it with an unreviewed branch | Re-copy the reviewed ref from `examples/consumer-workflow.yml`, then retry |
| Checkout or setup fails before the drill | The run's permissions and runner policy; the template requires `contents: read`, Ubuntu, and Windows hosted runners | Fix repository/organization Actions policy or runner availability; keep permissions read-only |
| Ubuntu passes but Windows fails (or the reverse) | The failing matrix leg's shell output and path formatting | Re-run that leg after checking the runner image; do not remove validation or switch to `pull_request_target` just to make it pass |
| Report/manifest/credential validation fails | The `Run Maintainer-Zero` logs for the first error and whether the output directory was reused | Start a fresh run and avoid hand-editing generated files; only upload a bundle after all three validators pass |
| No artifact is uploaded | Whether the job is green; upload uses `if: success()` and `if-no-files-found: error` by design | Read the Job Summary and fix the earlier failure; an unverified bundle is not published |
| Monthly run has not appeared | Schedules use UTC (`08:17` on the first day of each month) and run only from the default branch; GitHub may delay scheduled jobs | Confirm Actions are enabled and the repository has recent activity, then use `workflow_dispatch` for an immediate check |
| The report contains dependency names or findings you did not want to share | Privacy settings and the generated artifact contents; anonymization does not remove every repository-sensitive finding | Review and redact before sharing; Maintainer-Zero never uploads source files or writes to GitHub |

These checks diagnose workflow wiring, not project resilience. Maintainer-Zero remains an alpha, offline-first heuristic drill: a score is neither a security certification nor proof of real disaster recovery.

Before creating a release, use the read-only [release candidate workflow](.github/workflows/release-candidate.yml) on a `v*` tag or via manual dispatch. It verifies wheel/sdist artifacts outside the checkout and uploads them for review; it does not publish to PyPI or the Marketplace.

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

Bus-factor dashboards estimate contribution concentration; dependency scanners find package vulnerabilities. Maintainer-Zero combines local repository signals with a deterministic incident model and reviewable recovery drafts. See the [related-work audit](docs/NOVELTY_AUDIT.md) for adjacent tools and the limits of the dated search; this is not a claim of being the first or only implementation.

The checked-in scenario registry is available at maintainer_zero/scenario_registry.json. It is a versioned, data-only contract for scenario review; registry loading never executes an entrypoint or formula. See docs/SCENARIO_REGISTRY.md for contribution and safety rules.

## Contributing

Add a scenario with explicit assumptions, a deterministic test, and a short explanation of how its score is calculated. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Community

Use [Discussions](https://github.com/LittleChenLiya/maintainer-zero/discussions) for questions,
benchmark comparisons, and roadmap ideas; use the [support guide](SUPPORT.md) to choose the right
channel. Bug reports and declarative scenario proposals have sanitized issue forms. Please review
the [security policy](SECURITY.md) before sharing vulnerability or privacy details.
Please also follow the project [Code of Conduct](CODE_OF_CONDUCT.md) when participating.

## Share the project

Ready-to-publish English, Chinese, X/Twitter, and GitHub Discussions copy is in the [launch kit](docs/LAUNCH_KIT.md). Please keep the alpha/MVP and offline-by-default boundaries intact when sharing results.

If Maintainer-Zero supports your research, documentation, or benchmark, cite the project with the metadata in [CITATION.cff](CITATION.cff).

## License

MIT
