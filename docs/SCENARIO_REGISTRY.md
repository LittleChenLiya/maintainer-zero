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
- Registry and standalone scenario files are limited to 1 MiB and parsed as
  UTF-8 JSON before validation. Duplicate IDs and
  duplicate input names are rejected.
- Builtin entrypoints are restricted to the three reviewed functions shipped
  by the project; unknown entrypoints are rejected before any future executor
  could resolve them.
- Registry and standalone loaders accept only regular files and reject symlinked
  path components, Windows junctions/reparse points, and other special files,
  so validation cannot be redirected to an unexpected target.
- In-memory validation also rejects cyclic values and limits nested JSON-like
  structures to 64 levels before recursive copying or field validation.

Validate a contribution before opening a pull request:

    from maintainer_zero.scenario_registry import load_registry
    load_registry("path/to/registry.json")

也可以通过只读 CLI 校验完整注册表；该命令只读取 JSON，不执行任何 entrypoint、公式或仓库代码：

```powershell
maintainer-zero validate-registry maintainer_zero/scenario_registry.json
```

单个 data-only 场景仍可用 `validate-scenario PATH` 校验。校验失败返回退出码 2，成功只打印注册表身份、版本和场景数量。

需要人工快速审阅场景契约时，可使用只读 `describe-scenario PATH`。它输出触发窗口、输入来源、恢复动作、限制和执行模式；不会输出 entrypoint，不会导入或执行任何代码。加上 `--format json` 可生成机器可读摘要。

Each new scenario should include one blocking example, one negative example
with a verified fallback, and tests showing that the scenario is deterministic.
The registry intentionally does not claim to predict incident probability or
prove recovery; it records a reproducible drill contract for review.
