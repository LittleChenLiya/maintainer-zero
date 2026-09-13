from __future__ import annotations

import json

import pytest

from maintainer_zero.github_client import TransportResponse
from maintainer_zero.github_metadata import summarize_metadata
from maintainer_zero.metadata_provider import ReadOnlyProviderClient


def test_gitlab_next_page_beyond_request_limit_remains_partial():
    calls = []

    def fetch(path, params, timeout):
        calls.append((path, dict(params)))
        if not path.endswith("/issues"):
            return TransportResponse(200, b"[]", {})
        page = int(params["page"])
        return TransportResponse(
            200, json.dumps([{"iid": page}]), {"X-Next-Page": str(page + 1)}
        )

    payload = ReadOnlyProviderClient(
        "gitlab", fetch, max_pages=50, page_size=2
    ).collect("42")

    assert payload["collection"]["issues"] == {
        "available": True, "pages": 50, "truncated": True, "reason": "page_limit"
    }
    assert summarize_metadata(payload)["partial"] == ["issues"]
    assert len(payload["data"]["issues"]) == 50
    assert [params["page"] for path, params in calls if path.endswith("/issues")] == [
        str(page) for page in range(1, 51)
    ]


@pytest.mark.parametrize("header", ["²", "9" * 10_000, "-2", "0", "1"])
def test_gitlab_invalid_next_page_header_does_not_raise_or_add_requests(header):
    calls = []

    def fetch(path, params, timeout):
        calls.append((path, dict(params)))
        return TransportResponse(200, b"[]", {"X-Next-Page": header})

    payload = ReadOnlyProviderClient("gitlab", fetch).collect("42")

    assert len(calls) == 3
    assert all(status["pages"] == 1 for status in payload["collection"].values())
    assert all(status["available"] for status in payload["collection"].values())
    assert "partial" not in summarize_metadata(payload)


@pytest.mark.parametrize("name", ["Retry-After", "X-RateLimit-Reset"])
@pytest.mark.parametrize("value", ["²", "9" * 10_000])
def test_provider_unsafe_numeric_rate_limit_hints_remain_unknown(name, value):
    calls = []

    def fetch(path, params, timeout):
        calls.append(path)
        if path.endswith("/issues"):
            return TransportResponse(429, b"{}", {name: value})
        return TransportResponse(200, b"[]", {})

    payload = ReadOnlyProviderClient("forgejo", fetch).collect("acme/demo")

    assert len(calls) == 3
    assert payload["collection"]["issues"] == {
        "available": False, "pages": 0, "truncated": False, "reason": "rate_limited"
    }
    assert "issues" in summarize_metadata(payload)["unknown"]
    assert "issues" not in payload["data"]


def test_forgejo_does_not_use_gitlab_next_page_header():
    calls = []

    def fetch(path, params, timeout):
        calls.append((path, dict(params)))
        return TransportResponse(200, b"[]", {"X-Next-Page": "2"})

    payload = ReadOnlyProviderClient("forgejo", fetch).collect("acme/demo")

    assert len(calls) == 3
    assert all(status["pages"] == 1 for status in payload["collection"].values())
    assert "partial" not in summarize_metadata(payload)
