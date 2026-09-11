import json
import pytest
from maintainer_zero.scenario_registry import ScenarioSpecError, load_scenario, validate_scenario

def valid_scenario():
    return {"schema_version": 1, "id": "dependency-yanked", "version": "1.0.0", "title": "Dependency yanked", "description": "A declared dependency becomes unavailable.", "assumptions": ["The clean build has no private cache."], "inputs": [{"name": "days", "type": "integer", "required": True}], "events": [{"day": 0, "name": "Package yanked", "impact": "Install fails."}], "findings": [{"id": "cold-build", "severity": "high", "title": "Cold build blocked", "action": "Verify a mirror."}], "score": {"formula": "100 - 10 per unpinned dependency", "range": [0, 100]}}

def test_valid_scenario_is_deterministic_and_loadable(tmp_path):
    payload = valid_scenario()
    assert validate_scenario(payload) == payload
    path = tmp_path / "scenario.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert load_scenario(path)["id"] == "dependency-yanked"

@pytest.mark.parametrize("field", ["command", "entrypoint", "exec", "module", "script", "shell"])
def test_executable_fields_are_rejected(field):
    payload = valid_scenario()
    payload[field] = "unsafe"
    with pytest.raises(ScenarioSpecError, match="executable"):
        validate_scenario(payload)

def test_scenario_rejects_unordered_events_duplicate_findings_and_future_schema():
    payload = valid_scenario()
    payload["events"].append({"day": -1, "name": "invalid day", "impact": "bad"})
    with pytest.raises(ScenarioSpecError, match="non-negative"):
        validate_scenario(payload)
    payload = valid_scenario()
    payload["findings"].append(dict(payload["findings"][0]))
    with pytest.raises(ScenarioSpecError, match="unique"):
        validate_scenario(payload)
    payload = valid_scenario()
    payload["schema_version"] = 2
    with pytest.raises(ScenarioSpecError, match="unsupported"):
        validate_scenario(payload)
