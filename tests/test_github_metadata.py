import json

import pytest

from maintainer_zero.github_metadata import MetadataError, load_metadata, summarize_metadata, validate_metadata

def snapshot():
    return {"schema_version": 1, "permissions": {"issues": True, "pull_requests": False}, "data": {"issues": [{"number": 1}]}}

def test_summary_preserves_unknown_permissions_and_is_deterministic():
    expected = {"source": "github-metadata", "read_only": True, "permissions": {"issues": True, "pull_requests": False}, "fields": {"issues": 1, "pull_requests": None, "reviews": None, "releases": None}, "unknown": ["pull_requests", "reviews", "releases"]}
    assert summarize_metadata(snapshot()) == expected
    assert summarize_metadata(snapshot()) == expected

def test_validation_rejects_future_schema_and_unbounded_arrays():
    with pytest.raises(MetadataError, match="unsupported"):
        validate_metadata({**snapshot(), "schema_version": 2})
    with pytest.raises(MetadataError, match="bounded"):
        validate_metadata({**snapshot(), "data": {"issues": [None] * 5001}})

def test_load_metadata_reads_local_snapshot(tmp_path):
    path = tmp_path / "github.json"
    path.write_text(json.dumps(snapshot()), encoding="utf-8")
    assert load_metadata(path)["schema_version"] == 1

def test_summary_does_not_expose_tokens():
    payload = snapshot()
    payload["token"] = "do-not-store"
    summary = summarize_metadata(payload)
    assert summary["read_only"] is True
    assert "token" not in summary
