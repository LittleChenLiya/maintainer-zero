# Contributing

Please read the [Code of Conduct](CODE_OF_CONDUCT.md) before participating. Keep reports, fixtures,
and review comments respectful and free of secrets or private repository data.

1. Create a focused branch.
2. Keep scenario scoring deterministic and explainable.
3. Add or update tests for behavior changes.
4. Install the contributor test extra with `python -m pip install -e ".[test]"`.
5. Run `python -m pytest -q` before opening a pull request.

New scenarios should document: trigger, assumptions, inputs, score formula, limitations, and a recovery action. Never include real secrets or unredacted private repository data in fixtures.

Declarative community scenarios use the versioned JSON format checked by
`maintainer_zero.scenario_registry`. They may describe assumptions, ordered events,
findings, and a score formula, but must not contain executable fields such as
`command`, `module`, `script`, `shell`, or `exec`. Validate a scenario before review:

```powershell
maintainer-zero validate-scenario examples/scenarios/dependency-yanked.json
```
