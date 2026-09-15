import json

import pytest

from maintainer_zero.demos import DemoError, load_demo_suite, validate_demo_suite


def _suite():
    return json.loads(
        '{"schema_version": 1, "demos": [{'
        '"id": "demo-case", "scenario": "ci-outage",'
        '"before": {"path": "before", "name": "demo", "commits": 2,'
        '"contributors": {"a": 2}, "dependencies": [], "workflows": [],'
        '"codeowners": {}, "release_files": []},'
        '"after": {"path": "after", "name": "demo", "commits": 2,'
        '"contributors": {"a": 2}, "dependencies": [], "workflows": [],'
        '"codeowners": {}, "release_files": []},'
        '"lesson": "keep a fallback"}]}')


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("commits", True, "commits must be an integer"),
        ("commits", -1, "commits must be an integer"),
        ("contributors", ["a"], "contributors must be an object"),
        ("dependencies", [1], r"dependencies\[0\] must be a non-empty string"),
    ],
)
def test_snapshot_fields_are_type_checked(field, value, message):
    payload = _suite()
    payload["demos"][0]["before"][field] = value
    with pytest.raises(DemoError, match=message):
        validate_demo_suite(payload)


def test_contributor_counts_cannot_exceed_commits():
    payload = _suite()
    payload["demos"][0]["before"]["contributors"] = {"a": 3}
    with pytest.raises(DemoError, match="cannot exceed commits"):
        validate_demo_suite(payload)


@pytest.mark.parametrize("demo_id", ["Bad-ID", "bad_id", "", "x" * 65])
def test_demo_id_is_bounded_and_stable(demo_id):
    payload = _suite()
    payload["demos"][0]["id"] = demo_id
    with pytest.raises(DemoError, match="lowercase kebab-case"):
        validate_demo_suite(payload)


def test_unknown_top_level_or_demo_fields_are_rejected():
    payload = _suite()
    payload["unexpected"] = True
    with pytest.raises(DemoError, match="exactly schema_version and demos"):
        validate_demo_suite(payload)
    payload = _suite()
    payload["demos"][0]["command"] = "do-not-run"
    with pytest.raises(DemoError, match="exactly the demo fields"):
        validate_demo_suite(payload)


def test_loader_rejects_oversized_input(tmp_path):
    path = tmp_path / "large.json"
    path.write_bytes(b"x" * (1_048_576 + 1))
    with pytest.raises(DemoError, match="exceeds 1048576 bytes"):
        load_demo_suite(path)
