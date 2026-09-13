from __future__ import annotations

import json

import pytest

from maintainer_zero.github_client import TransportResponse
from maintainer_zero.github_metadata import MetadataError, summarize_metadata
from maintainer_zero.metadata_provider import (
    ProviderClientError,
    ReadOnlyProviderClient,
    _validate_response_shape,
    provider_paths,
    validate_provider_identifier,
)


def test_gitlab_paths_are_explicit_and_numeric_project_scoped():
    assert provider_paths("gitlab", "42", include_repository=True) == {
        "project": "/api/v4/projects/42",
        "issues": "/api/v4/projects/42/issues",
        "merge_requests": "/api/v4/projects/42/merge_requests",
        "releases": "/api/v4/projects/42/releases",
    }
    with pytest.raises(ProviderClientError, match="numeric"):
        validate_provider_identifier("gitlab", "group/project")
    with pytest.raises(ProviderClientError, match="reviews"):
        provider_paths("gitlab", "42", reviews_pr=1)


def test_forgejo_paths_are_explicit_and_slug_scoped():
    paths = provider_paths("forgejo", "acme/demo", include_repository=True, reviews_pr=7)
    assert paths["repository"] == "/api/v1/repos/acme/demo"
    assert paths["pulls"] == "/api/v1/repos/acme/demo/pulls"
    assert paths["reviews"] == "/api/v1/repos/acme/demo/pulls/7/reviews"
    with pytest.raises(ProviderClientError, match="OWNER/REPOSITORY"):
        validate_provider_identifier("forgejo", "../secret")


def test_gitlab_client_paginates_and_maps_records_without_network():
    calls = []

    def fetch(path, params, timeout):
        calls.append((path, dict(params), timeout))
        page = int(params["page"])
        body = [{"iid": page, "state": "opened", "author": {"username": "private"}}] if page < 2 else []
        return TransportResponse(200, json.dumps(body), {"Link": ""})

    payload = ReadOnlyProviderClient("gitlab", fetch, page_size=1).collect("42")
    assert payload["provider"] == "gitlab"
    assert payload["data"]["issues"] == [{"number": 1, "state": "opened"}]
    assert len(calls) == 6
    assert {path for path, _, _ in calls} == {
        "/api/v4/projects/42/issues",
        "/api/v4/projects/42/merge_requests",
        "/api/v4/projects/42/releases",
    }
    assert all(timeout == 5.0 for _, _, timeout in calls)


def test_forgejo_client_preserves_rate_limit_hints_and_unknowns():
    def fetch(path, params, timeout):
        if path.endswith("/issues"):
            return TransportResponse(429, b"{}", {"Retry-After": "9", "X-RateLimit-Reset": "1700000000", "X-Leak": "secret"})
        return TransportResponse(200, b"[]", {})

    payload = ReadOnlyProviderClient("forgejo", fetch).collect("acme/demo")
    status = payload["collection"]["issues"]
    assert status["available"] is False
    assert status["reason"] == "rate_limited"
    assert status["retry_after_seconds"] == 9
    assert status["rate_limit_reset_epoch"] == 1700000000
    assert "X-Leak" not in json.dumps(payload)
    assert "issues" in summarize_metadata(payload)["unknown"]


def test_forgejo_client_uses_forgejo_limit_pagination_parameter():
    calls = []

    def fetch(path, params, timeout):
        calls.append(dict(params))
        return TransportResponse(200, b"[]", {})

    ReadOnlyProviderClient("forgejo", fetch, page_size=17).collect("acme/demo")

    assert calls
    assert all(params["limit"] == "17" for params in calls)
    assert all("per_page" not in params for params in calls)


def test_gitlab_client_honors_x_next_page_when_page_is_short():
    calls = []

    def fetch(path, params, timeout):
        calls.append((path, dict(params)))
        page = int(params["page"])
        body = [{"iid": page}] if page < 2 else []
        headers = {"X-Next-Page": "2"} if page == 1 else {}
        return TransportResponse(200, json.dumps(body), headers)

    payload = ReadOnlyProviderClient("gitlab", fetch, page_size=25).collect("42")

    assert payload["data"]["issues"] == [{"number": 1}]
    assert [params["page"] for path, params in calls if path.endswith("/issues")] == ["1", "2"]


def test_provider_client_rejects_duplicate_or_nested_records_fail_closed():
    duplicate = lambda *_: TransportResponse(200, b'[{"iid":1,"iid":2}]', {})
    payload = ReadOnlyProviderClient("gitlab", duplicate).collect("42")
    assert payload["permissions"]["issues"] is False
    nested = lambda *_: TransportResponse(200, b'[{"iid":1,"author":{"id":2}}]', {})
    payload = ReadOnlyProviderClient("gitlab", nested).collect("42")
    assert payload["permissions"]["issues"] is True
    assert payload["data"]["issues"] == [{"number": 1}]


def test_provider_client_rejects_unbounded_integers_and_headers_without_raising():
    huge = lambda *_: TransportResponse(200, json.dumps([{"iid": 10**100}]), {})
    payload = ReadOnlyProviderClient("gitlab", huge).collect("42")
    assert payload["permissions"]["issues"] is False
    giant_header = lambda *_: TransportResponse(429, b"{}", {"Retry-After": "9" * 10000, "X-RateLimit-Reset": "8" * 10000})
    payload = ReadOnlyProviderClient("forgejo", giant_header).collect("acme/demo")
    assert payload["collection"]["issues"]["reason"] == "rate_limited"
    assert "retry_after_seconds" not in payload["collection"]["issues"]


def test_provider_response_validator_detects_cycles_with_empty_active_set():
    value = {}
    value["self"] = value
    with pytest.raises(ValueError, match="cyclic"):
        _validate_response_shape(value, active=set())
