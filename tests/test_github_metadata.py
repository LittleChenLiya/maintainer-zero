import json

import pytest

from maintainer_zero.github_metadata import MetadataError, load_metadata, summarize_metadata, validate_metadata

def snapshot():
    return {"schema_version": 1, "permissions": {"issues": True, "pull_requests": False}, "data": {"issues": [{"number": 1}]}}

def test_summary_preserves_unknown_permissions_and_is_deterministic():
    expected = {"source": "github-metadata", "read_only": True, "permissions": {"issues": True, "pull_requests": False}, "fields": {"repository": None, "issues": 1, "pull_requests": None, "reviews": None, "releases": None}, "unknown": ["repository", "pull_requests", "reviews", "releases"]}
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

def test_validation_rejects_unknown_resources_and_non_object_records():
    with pytest.raises(MetadataError, match="unsupported resource"):
        validate_metadata({**snapshot(), "data": {"unknown": []}})
    with pytest.raises(MetadataError, match="bounded"):
        validate_metadata({**snapshot(), "data": {"issues": ["not-an-object"]}})

def test_load_metadata_rejects_oversized_files(tmp_path):
    path = tmp_path / "large.json"
    path.write_bytes(b"{" + b"x" * 10_000_000 + b"}")
    with pytest.raises(MetadataError, match="exceeds"):
        load_metadata(path)

def test_collection_status_is_bounded():
    payload = {**snapshot(), "collection": {"issues": {"available": True, "pages": 51, "truncated": False}}}
    with pytest.raises(MetadataError, match="pages"):
        validate_metadata(payload)

def test_summary_does_not_expose_tokens():
    payload = snapshot()
    payload["token"] = "do-not-store"
    with pytest.raises(MetadataError, match="top-level"):
        summarize_metadata(payload)

def test_repository_descriptor_is_scalar_and_summarized_without_raw_lists():
    payload = snapshot()
    payload["permissions"]["repository"] = True
    payload["data"]["repository"] = {"default_branch": "main", "visibility": "public", "archived": False}
    summary = summarize_metadata(payload)
    assert summary["fields"]["repository"] == payload["data"]["repository"]
    assert "repository" not in summary["unknown"]

def test_repository_descriptor_rejects_nested_or_unknown_fields():
    payload = snapshot()
    payload["data"]["repository"] = {"owner": {"login": "x"}}
    with pytest.raises(MetadataError, match="repository"):
        validate_metadata(payload)


def test_metadata_rejects_nonstandard_json_numbers(tmp_path):
    payload = snapshot()
    payload["data"]["issues"][0]["number"] = float("nan")
    with pytest.raises(MetadataError, match="non-finite"):
        validate_metadata(payload)

    path = tmp_path / "nan.json"
    path.write_text('{"schema_version": 1, "permissions": {}, "data": {"issues": [{"n": NaN}]}}', encoding="utf-8")
    with pytest.raises(MetadataError, match="non-standard"):
        load_metadata(path)

def test_summary_marks_truncated_resources_as_partial():
    payload = {**snapshot(), "collection": {"issues": {"available": True, "pages": 5, "truncated": True}}}
    assert summarize_metadata(payload)["partial"] == ["issues"]

def test_summary_preserves_only_bounded_collection_status_fields():
    payload = {**snapshot(), "collection": {"issues": {"available": False, "pages": 0, "truncated": False, "reason": "rate_limited", "retry_after_seconds": 30, "rate_limit_reset_epoch": 1700000000}}}
    assert summarize_metadata(payload)["collection"] == {"issues": {"available": False, "pages": 0, "truncated": False, "reason": "rate_limited", "retry_after_seconds": 30, "rate_limit_reset_epoch": 1700000000}}

def test_metadata_rejects_unbounded_collection_scheduling_hints():
    with pytest.raises(MetadataError, match="retry_after_seconds"):
        validate_metadata({**snapshot(), "collection": {"issues": {"available": False, "pages": 0, "truncated": False, "retry_after_seconds": 86401}}})
