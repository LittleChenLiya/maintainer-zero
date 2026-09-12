import json

import pytest

from maintainer_zero.github_http import GitHubHTTPError, GitHubHTTPTransport, HTTPTransportConfig


class FakeResponse:
    status = 200
    headers = {"X-Test": "ok"}

    def read(self, limit):
        assert limit > 0
        return json.dumps([{"number": 1}]).encode()


def test_transport_is_get_only_and_does_not_expose_token():
    calls = []

    def opener(request, timeout):
        calls.append((request, timeout))
        return FakeResponse()

    transport = GitHubHTTPTransport(token="secret-token", opener=opener)
    response = transport("/repos/acme/demo/issues", {"page": "1"}, 2.5)
    assert response.status_code == 200
    assert calls[0][0].method == "GET"
    assert calls[0][0].get_header("Authorization") == "Bearer secret-token"
    assert "secret-token" not in repr(response)
    assert "secret-token" not in repr(transport)
    assert "token_present=True" in repr(transport)
    assert calls[0][1] == 2.5


def test_transport_rejects_unapproved_paths_and_unsafe_config():
    with pytest.raises(GitHubHTTPError, match="non-whitelisted"):
        GitHubHTTPTransport()("/repos/acme/demo/issues?state=all", {}, 1)
    with pytest.raises(GitHubHTTPError, match="https"):
        GitHubHTTPTransport(config=type("Config", (), {"api_base": "http://localhost", "user_agent": "x", "max_response_bytes": 1})())
    with pytest.raises(GitHubHTTPError, match="single-line"):
        GitHubHTTPTransport(token="bad\nsecret")
    with pytest.raises(GitHubHTTPError, match="single-line"):
        GitHubHTTPTransport(token="bad\x00secret")
    with pytest.raises(GitHubHTTPError, match="single-line"):
        GitHubHTTPTransport(config=HTTPTransportConfig(user_agent="maintainer-zero\tclient"))
    with pytest.raises(GitHubHTTPError, match="non-whitelisted"):
        GitHubHTTPTransport()("/repos/../secret/issues", {}, 1)
    for base in ("https://user:pass@api.github.com", "https://api.github.com?token=leak", "https://[bad"):
        with pytest.raises(GitHubHTTPError, match="https"):
            GitHubHTTPTransport(config=HTTPTransportConfig(api_base=base))
    with pytest.raises(GitHubHTTPError, match="max_response_bytes"):
        GitHubHTTPTransport(config=HTTPTransportConfig(max_response_bytes=1_000_001))


def test_environment_token_requires_explicit_opt_in(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "secret")
    without_opt_in = GitHubHTTPTransport.from_environment()
    assert without_opt_in.token is None
    with_opt_in = GitHubHTTPTransport.from_environment(allow_environment=True)
    assert with_opt_in.token == "secret"


def test_transport_rejects_unbounded_timeout():
    transport = GitHubHTTPTransport()
    with pytest.raises(GitHubHTTPError, match="timeout"):
        transport("/repos/acme/demo/issues", {}, 61)
