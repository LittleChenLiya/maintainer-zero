import json
from pathlib import Path

import pytest

from maintainer_zero.scenario_registry import (
    ScenarioRegistryError,
    ScenarioSpecError,
    load_bundled_registry,
    load_registry,
    load_scenario,
    scenario_ids,
    scenario_summary,
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
    scenario = dict(registry["scenarios"][0], execution={"mode": "builtin", "entrypoint": "maintainer_zero.scenarios:unknown"})
    with pytest.raises(ScenarioRegistryError, match="approved builtin"):
        validate_scenario(scenario)
    scenario = dict(registry["scenarios"][0], execution={"mode": "declarative", "entrypoint": "ignored:entrypoint"})
    with pytest.raises(ScenarioRegistryError, match="must not declare"):
        validate_scenario(scenario)


def test_load_registry_bounds_untrusted_file(tmp_path):
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(load_bundled_registry()), encoding="utf-8")
    with pytest.raises(ScenarioRegistryError, match="exceeds"):
        load_registry(path, max_bytes=10)
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ScenarioRegistryError, match="JSON object"):
        load_registry(path)


def test_load_scenario_bounds_untrusted_file(tmp_path):
    path = tmp_path / "scenario.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="max_bytes"):
        load_scenario(path, max_bytes=0)
    with pytest.raises(ScenarioSpecError, match="exceeds"):
        load_scenario(path, max_bytes=1)


def test_loaders_reject_directories_and_symlinks(tmp_path):
    with pytest.raises(ScenarioRegistryError, match="regular file"):
        load_registry(tmp_path)
    target = tmp_path / "target.json"
    target.write_text(json.dumps(load_bundled_registry()), encoding="utf-8")
    link = tmp_path / "registry-link.json"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")
    with pytest.raises(ScenarioRegistryError, match="regular file"):
        load_registry(link)


def test_scenario_summary_is_stable_and_does_not_expose_entrypoint():
    summary = scenario_summary(load_bundled_registry()["scenarios"][0])
    assert summary["id"] == "ci-outage"
    assert summary["input_sources"] == {"release_files": "observed", "workflows": "observed"}
    assert summary["execution_mode"] == "builtin"
    assert "entrypoint" not in summary


def test_legacy_scenario_summary_derives_bounded_trigger_and_actions():
    summary = scenario_summary(load_scenario(EXAMPLES / "dependency-yanked.json"))
    assert summary["trigger"] == {"type": "legacy-event-sequence", "duration_days": 1}
    assert summary["recovery_actions"] == ["Verify a mirror, lock source, or tested replacement."]
