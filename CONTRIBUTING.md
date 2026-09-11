# Contributing

1. Create a focused branch.
2. Keep scenario scoring deterministic and explainable.
3. Add or update tests for behavior changes.
4. Run `python -m pytest -q` before opening a pull request.

New scenarios should document: trigger, assumptions, inputs, score formula, limitations, and a recovery action. Never include real secrets or unredacted private repository data in fixtures.
