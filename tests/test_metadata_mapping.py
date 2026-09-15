from __future__ import annotations

import pytest

from maintainer_zero.github_metadata import MetadataError
from maintainer_zero.metadata_mapping import normalize_metadata


def test_normalize_gitlab_project_and_merge_requests_to_canonical_snapshot():
    raw = {
        "schema_version": 1,
        "permissions": {"project": True, "issues": True, "merge_requests": True},
        "data": {
            "project": {"default_branch": "main", "star_count": 4, "issues_enabled": True},
            "issues": [{"iid": 7, "state": "opened", "user_notes_count": 2}],
            "merge_requests": [{"iid": 8, "merged_at": None}],
        },
    }
    result = normalize_metadata("gitlab", raw)
    assert result == {
        "schema_version": 1,
        "provider": "gitlab",
        "permissions": {"repository": True, "issues": True, "pull_requests": True},
        "data": {
            "repository": {"default_branch": "main", "has_issues": True, "stargazers_count": 4},
            "issues": [{"comments": 2, "number": 7, "state": "opened"}],
            "pull_requests": [{"merged_at": None, "number": 8}],
        },
    }


def test_normalize_forgejo_projects_safe_scalar_fields_only():
    raw = {
        "schema_version": 1,
        "permissions": {"repository": True, "pulls": True},
        "data": {
            "repository": {"stars_count": 12, "has_issues": True},
            "pulls": [{"number": 3, "state": "open"}],
        },
    }
    result = normalize_metadata("forgejo", raw)
    assert result["data"]["repository"] == {"has_issues": True, "stargazers_count": 12}
    assert result["data"]["pull_requests"] == [{"number": 3, "state": "open"}]


@pytest.mark.parametrize(
    ("provider", "raw", "message"),
    [
        ("gitlab", {"schema_version": 1, "permissions": {"project": True, "repository": False}, "data": {}}, "ambiguous"),
        ("gitlab", {"schema_version": 1, "permissions": {"issues": True}, "data": {"issues": [{"iid": 1, "number": 2}]}}, "ambiguous"),
        ("forgejo", {"schema_version": 1, "permissions": {"issues": True}, "data": {"issues": [{"body": "secret"}]}}, "unsupported provider field"),
        ("github", {"schema_version": 1, "provider": "gitlab", "permissions": {}, "data": {}}, "does not match"),
    ],
)
def test_normalize_rejects_ambiguous_or_sensitive_adapter_input(provider, raw, message):
    with pytest.raises(MetadataError, match=message):
        normalize_metadata(provider, raw)


def test_normalize_rejects_nested_values_and_unknown_adapter_fields():
    raw = {
        "schema_version": 1,
        "permissions": {"issues": True},
        "data": {"issues": [{"number": 1, "author": {"id": 9}}]},
        "token": "must-not-cross-boundary",
    }
    with pytest.raises(MetadataError, match="adapter fields"):
        normalize_metadata("github", raw)

