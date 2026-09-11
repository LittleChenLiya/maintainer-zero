import json
from pathlib import Path

import pytest

from maintainer_zero.scenario_registry import (
    ScenarioRegistryError,
    load_bundled_registry,
    load_registry,
    load_scenario,
    scenario_ids,
    validate_registry,
    validate_scenario,
)

EXAMPLES = Path(__file__).parents[1] / "examples" / "scenarios"


def test_bundled_registry_is_versioned_and_deterministic():
    registry = load_bundled_registry()
    assert registry["schema_version"] == 1
    assert scenario_ids(registry) == ("ci-outage", "dependency-yanked", "maintainer-zero")
    assert all(item["execution"]["mode"] == "builtin" for item in registry["scenarios"])


def test_all_community_examples_are_bounded_and_loadable():
    examples = sorted(EXAMPLES.glob("*.json"))
    assert len(examples) >= 10
    loaded = [load_scenario(path) for path in examples]
    assert [item["id"] for item in loaded] == sorted(item["id"] for item in loaded)
    assert all(item["schema_version"] == 1 for item in loaded)
    assert all(
        item.get("execution", {}).get("mode") == "declarative"
        or "execution" not in item
        for item in loaded
    )


def test_registry_rejects_duplicate_or_unsupported_scenarios():
    registry = load_bundled_registry()
    registry["scenarios"].append(registry["scenarios"][0])
    with pytest.raises(ScenarioRegistryError, match="duplicate scenario id"):
        validate_registry(registry)
    invalid = dict(registry["scenarios"][0], schema_version=2)
    with pytest.raises(ScenarioRegistryError, match="unsupported scenario schema_version"):
        validate_scenario(invalid)


def test_registry_requires_safe_execution_contract():
    registry = load_bundled_registry()
    scenario = dict(registry["scenarios"][0], id="Bad Name")
    with pytest.raises(ScenarioRegistryError, match="scenario.id"):
        validate_scenario(scenario)
    scenario = dict(registry["scenarios"][0], execution={"mode": "python", "entrypoint": "os:system"})
    with pytest.raises(ScenarioRegistryError, match="execution mode"):
        validate_scenario(scenario)


def test_load_registry_bounds_untrusted_file(tmp_path):
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(load_bundled_registry()), encoding="utf-8")
    with pytest.raises(ScenarioRegistryError, match="exceeds"):
        load_registry(path, max_bytes=10)
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ScenarioRegistryError, match="JSON object"):
        load_registry(path)
