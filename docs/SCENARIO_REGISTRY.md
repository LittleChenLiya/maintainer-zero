# Versioned scenario registry

Maintainer-Zero keeps community scenario descriptions in a small, reviewable
JSON format. The first registry is in maintainer_zero/scenario_registry.json.
It describes the three built-in drills without changing their executable
scoring functions. A registry is metadata and policy, not a plugin loader.
The `examples/scenarios/` directory also contains a small community catalog
of standalone declarations (review queue, signing, package registry,
security, documentation, artifact, tracker, domain, and localization drills).
These examples are intentionally data-only: they document a drill contract
but are not loaded as executable plugins.

## Safety and review contract

- schema_version is currently 1; incompatible changes require a new version.
- Each scenario has a lowercase, stable id and a SemVer version.
- assumptions, inputs, score, recovery_actions, and limitations are required
  so a contribution states its evidence boundary and escape path.
- Input sources distinguish observed, assumed, configuration, and unknown;
  missing evidence must not be silently treated as healthy.
- Scores declare the bounded [0, 100] range and an explanatory formula.
- Execution is limited to reviewed builtin or data-only declarative modes.
  Registry loading never imports an entrypoint, executes a subprocess, or
  evaluates a formula.
- Local files are size-bounded and parsed as UTF-8 JSON. Duplicate IDs and
  duplicate input names are rejected.

Validate a contribution before opening a pull request:

    from maintainer_zero.scenario_registry import load_registry
    load_registry("path/to/registry.json")

Each new scenario should include one blocking example, one negative example
with a verified fallback, and tests showing that the scenario is deterministic.
The registry intentionally does not claim to predict incident probability or
prove recovery; it records a reproducible drill contract for review.
