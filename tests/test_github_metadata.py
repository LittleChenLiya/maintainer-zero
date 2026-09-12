import json
import os
from types import SimpleNamespace

import pytest

from maintainer_zero.github_metadata import MetadataError, load_metadata, summarize_metadata, validate_metadata

def snapshot():
    return {"schema_version": 1, "permissions": {"issues": True, "pull_requests": False}, "data": {"issues": [{"number": 1}]}}

def test_summary_preserves_unknown_permissions_and_is_deterministic():
    expected = {"source": "github-metadata", "read_only": True, "permissions": {"issues": True, "pull_requests": False}, "fields": {"repository": None, "issues": 1, "pull_requests": None, "reviews": None, "releases": None}, "unknown": ["repository", "pull_requests", "reviews", "releases"]}
    assert summarize_metadata(snapshot()) == expected
    assert summarize_metadata(snapshot()) == expected


def test_provider_neutral_snapshot_preserves_declared_provider():
    payload = {**snapshot(), "provider": "gitlab"}
    summary = summarize_metadata(payload)
    assert summary["provider"] == "gitlab"
    assert summary["source"] == "gitlab-metadata"


def test_provider_neutral_snapshot_rejects_unknown_provider():
    with pytest.raises(MetadataError, match="provider"):
        validate_metadata({**snapshot(), "provider": "unknown-forge"})


def test_provider_neutral_snapshot_rejects_non_string_provider():
    with pytest.raises(MetadataError, match="provider"):
        validate_metadata({**snapshot(), "provider": {"name": "gitlab"}})

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


def test_validation_rejects_raw_github_record_fields_and_nested_values():
    raw = {
        "number": 1,
        "state": "open",
        "body": "token=should-not-be-stored",
        "user": {"login": "private-person"},
    }
    with pytest.raises(MetadataError, match="unsupported field"):
        validate_metadata({**snapshot(), "data": {"issues": [raw]}})


def test_validation_accepts_only_projected_scalar_resource_fields():
    payload = {
        "schema_version": 1,
        "permissions": {"pull_requests": True, "reviews": True, "releases": True},
        "data": {
            "pull_requests": [{"number": 2, "state": "closed", "merged_at": None}],
            "reviews": [{"id": 9, "state": "approved", "commit_id": "abc"}],
            "releases": [{"id": 3, "draft": False, "published_at": "2026-01-01T00:00:00Z"}],
        },
    }
    assert validate_metadata(payload) == payload

def test_load_metadata_rejects_oversized_files(tmp_path):
    path = tmp_path / "large.json"
    path.write_bytes(b"{" + b"x" * 10_000_000 + b"}")
    with pytest.raises(MetadataError, match="exceeds"):
        load_metadata(path)


def test_load_metadata_rejects_non_regular_file(tmp_path):
    directory = tmp_path / "github.json"
    directory.mkdir()
    with pytest.raises(MetadataError, match="regular file"):
        load_metadata(directory)


def test_load_metadata_rejects_symlink(tmp_path):
    target = tmp_path / "real.json"
    target.write_text(json.dumps(snapshot()), encoding="utf-8")
    link = tmp_path / "github.json"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")
    with pytest.raises(MetadataError, match="regular file"):
        load_metadata(link)


def test_load_metadata_rejects_symlinked_parent(tmp_path):
    real = tmp_path / "real-parent"
    real.mkdir()
    (real / "github.json").write_text(json.dumps(snapshot()), encoding="utf-8")
    parent = tmp_path / "linked-parent"
    try:
        parent.symlink_to(real, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")
    with pytest.raises(MetadataError, match="symlink"):
        load_metadata(parent / "github.json")


def test_load_metadata_rejects_descriptor_redirect_before_parsing(tmp_path, monkeypatch):
    path = tmp_path / "github.json"
    path.write_text(json.dumps(snapshot()), encoding="utf-8")
    original_fstat = os.fstat

    def mismatched_fstat(fd):
        info = original_fstat(fd)
        return SimpleNamespace(
            st_mode=info.st_mode,
            st_file_attributes=getattr(info, "st_file_attributes", 0),
            st_dev=info.st_dev,
            st_ino=info.st_ino + 1,
            st_size=info.st_size,
        )

    monkeypatch.setattr("maintainer_zero.github_metadata.os.fstat", mismatched_fstat)
    with pytest.raises(MetadataError, match="changed during open"):
        load_metadata(path)


def test_load_metadata_rejects_duplicate_json_keys(tmp_path):
    path = tmp_path / "duplicate.json"
    path.write_text(
        '{"schema_version":1,"schema_version":1,"permissions":{},"data":{}}',
        encoding="utf-8",
    )
    with pytest.raises(MetadataError, match="duplicate"):
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


def test_metadata_rejects_cyclic_in_memory_values():
    payload = snapshot()
    payload["data"]["issues"][0]["self"] = payload["data"]["issues"][0]
    with pytest.raises(MetadataError, match="cyclic"):
        validate_metadata(payload)


def test_metadata_rejects_excessive_nesting_without_recursion_error(tmp_path):
    nested = "[" * 70 + "0" + "]" * 70
    payload = (
        '{"schema_version":1,"permissions":{"issues":true},'
        f'"data":{{"issues":[{{"nested":{nested}}}]}}}}'
    )
    path = tmp_path / "deep.json"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(MetadataError, match="nesting"):
        load_metadata(path)
