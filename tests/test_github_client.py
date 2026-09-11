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

def test_client_rejects_unapproved_paths_and_bounds_response():
    client = ReadOnlyGitHubClient(lambda *_: TransportResponse(200, b"[]"), max_response_bytes=2)
    with pytest.raises(GitHubClientError, match="unsupported"):
        client.collect({"issues": "/repos/acme/demo/issues?state=all"})
    payload = ReadOnlyGitHubClient(lambda *_: TransportResponse(200, b"[123]") , max_response_bytes=2).collect({"issues": "/repos/acme/demo/issues"})
    assert payload["collection"]["issues"]["reason"] == "response_too_large"
