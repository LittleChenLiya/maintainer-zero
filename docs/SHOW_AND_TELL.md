# Show-and-tell: run your first Maintainer-Zero continuity drill

Maintainer-Zero is built around one uncomfortable continuity question: if the core maintainer disappears for 90 days, can the project still ship a security fix?

This is a hands-on invitation to run a first, sanitized drill and show what it reveals.

## Try it in 30 seconds

```sh
git clone https://github.com/LittleChenLiya/maintainer-zero.git
cd maintainer-zero
python -m pip install -e .
maintainer-zero demo
```

To inspect a local checkout, run `maintainer-zero simulate /path/to/repo --scenario all --output .continuity` and open `.continuity/report.html`.

## Share one finding

Reply with only a sanitized summary:

- scenario (`maintainer-zero`, `dependency-yanked`, or `ci-outage`)
- one continuity gap the drill exposed
- the recovery action you would take
- Maintainer-Zero version and platform

Please do not post tokens, private URLs, contributor names, full dependency inventories, or private repository contents.

Maintainer-Zero is an alpha/offline-first MVP. Scores are heuristics; this is not a security certification, not proof of real hosted-runner disaster recovery, and the tool never writes to GitHub. If you find a false positive or a missing scenario, open an issue or propose a data-only scenario using [CONTRIBUTING.md](../CONTRIBUTING.md).

Project: https://github.com/LittleChenLiya/maintainer-zero

Releases: https://github.com/LittleChenLiya/maintainer-zero/releases
