import json

import pytest

from maintainer_zero.github_client import GitHubClientError, ReadOnlyGitHubClient, TransportResponse

def test_client_paginates_and_preserves_collection_status():
    calls = []
    def fetch(path, params, timeout):
        calls.append((path, dict(params), timeout))
        page = int(params["page"])
        return TransportResponse(200, json.dumps([{"number": page}] if page < 3 else []))
    payload = ReadOnlyGitHubClient(fetch, page_size=1).collect({"issues": "/repos/acme/demo/issues"})
    assert payload["data"]["issues"] == [{"number": 1}, {"number": 2}]
    assert payload["collection"]["issues"]["pages"] == 3
    assert len(calls) == 3 and calls[0][2] == 5.0

@pytest.mark.parametrize("status, reason", [(403, "forbidden_or_rate_limited"), (429, "rate_limited"), (500, "http_500")])
def test_client_degrades_unavailable_resource(status, reason):
    payload = ReadOnlyGitHubClient(lambda *_: TransportResponse(status, b"{}")).collect({"issues": "/repos/acme/demo/issues"})
    assert payload["permissions"]["issues"] is False
    assert "issues" not in payload["data"]
    assert payload["collection"]["issues"]["reason"] == reason

def test_client_preserves_bounded_rate_limit_scheduling_hints():
    payload = ReadOnlyGitHubClient(
        lambda *_: TransportResponse(429, b"{}", {"Retry-After": "37", "X-RateLimit-Reset": "1700000000", "X-Leak": "ignore"})
    ).collect({"issues": "/repos/acme/demo/issues"})
    status = payload["collection"]["issues"]
    assert status["retry_after_seconds"] == 37
    assert status["rate_limit_reset_epoch"] == 1700000000
    assert "X-Leak" not in status

def test_client_discards_unbounded_or_malformed_rate_limit_hints():
    payload = ReadOnlyGitHubClient(
        lambda *_: TransportResponse(403, b"{}", {"Retry-After": "999999", "X-RateLimit-Reset": "not-an-epoch"})
    ).collect({"issues": "/repos/acme/demo/issues"})
    assert "retry_after_seconds" not in payload["collection"]["issues"]
    assert "rate_limit_reset_epoch" not in payload["collection"]["issues"]

def test_client_rejects_unapproved_paths_and_bounds_response():
    client = ReadOnlyGitHubClient(lambda *_: TransportResponse(200, b"[]"), max_response_bytes=2)
    with pytest.raises(GitHubClientError, match="unsupported"):
        client.collect({"issues": "/repos/acme/demo/issues?state=all"})
    payload = ReadOnlyGitHubClient(lambda *_: TransportResponse(200, b"[123]") , max_response_bytes=2).collect({"issues": "/repos/acme/demo/issues"})
    assert payload["collection"]["issues"]["reason"] == "response_too_large"


def test_client_validates_bounds_before_any_fetch():
    calls = []
    with pytest.raises(GitHubClientError, match="timeout"):
        ReadOnlyGitHubClient(lambda *_: calls.append(1), timeout_seconds=float("inf"))
    with pytest.raises(GitHubClientError, match="max_pages"):
        ReadOnlyGitHubClient(lambda *_: calls.append(1), max_pages=51)
    with pytest.raises(GitHubClientError, match="unsupported metadata path"):
        ReadOnlyGitHubClient(lambda *_: calls.append(1)).collect({"issues": "/repos/acme/../issues"})
    assert calls == []


def test_client_rejects_non_object_records():
    payload = ReadOnlyGitHubClient(lambda *_: TransportResponse(200, b"[1]")).collect({"issues": "/repos/acme/demo/issues"})
    assert payload["permissions"]["issues"] is False
    assert payload["collection"]["issues"]["reason"] == "invalid_record"


def test_client_projects_array_records_to_data_only_fields():
    raw = {
        "number": 7,
        "state": "open",
        "created_at": "2026-01-01T00:00:00Z",
        "body": "token=should-not-be-stored",
        "user": {"login": "private-person"},
        "html_url": "https://github.example/private",
        "labels": [{"name": "secret-label"}],
    }
    payload = ReadOnlyGitHubClient(
        lambda *_: TransportResponse(200, json.dumps([raw]))
    ).collect({"issues": "/repos/acme/demo/issues"})
    assert payload["data"]["issues"] == [{
        "created_at": "2026-01-01T00:00:00Z",
        "number": 7,
        "state": "open",
    }]
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "should-not-be-stored" not in serialized
    assert "private-person" not in serialized
    assert "html_url" not in serialized


def test_client_rejects_nonstandard_numbers_in_object_and_array_payloads():
    repository = ReadOnlyGitHubClient(
        lambda *_: TransportResponse(200, b'{"open_issues_count": NaN}')
    ).collect({"repository": "/repos/acme/demo"})
    assert repository["collection"]["repository"]["reason"] == "invalid_json"

    issues = ReadOnlyGitHubClient(
        lambda *_: TransportResponse(200, b'[{"number": Infinity}]')
    ).collect({"issues": "/repos/acme/demo/issues"})
    assert issues["collection"]["issues"]["reason"] == "invalid_json"

    overflowing_repository = ReadOnlyGitHubClient(
        lambda *_: TransportResponse(200, b'{"open_issues_count": 1e999}')
    ).collect({"repository": "/repos/acme/demo"})
    assert overflowing_repository["collection"]["repository"]["reason"] == "invalid_json"

    overflowing_issues = ReadOnlyGitHubClient(
        lambda *_: TransportResponse(200, b'[{"number": 1e999}]')
    ).collect({"issues": "/repos/acme/demo/issues"})
    assert overflowing_issues["collection"]["issues"]["reason"] == "invalid_json"


def test_client_rejects_deep_response_payloads_without_raising():
    nested = "[" * 70 + "0" + "]" * 70
    response = ReadOnlyGitHubClient(
        lambda *_: TransportResponse(200, f"[{nested}]".encode())
    ).collect({"issues": "/repos/acme/demo/issues"})
    assert response["collection"]["issues"]["reason"] == "invalid_json"
