from __future__ import annotations

import json
from urllib.error import URLError

import pytest

from maintainer_zero.provider_http import (
    DEFAULT_USER_AGENT,
    ProviderHTTPError,
    ProviderHTTPTransport,
    ProviderHTTPTransportConfig,
)


class FakeResponse:
    status = 200
    headers = {"Link": '<https://gitlab.example/api/v4/projects/42/issues?page=2>; rel="next"', "X-Secret": "drop"}

    def read(self, limit):
        assert limit > 0
        return json.dumps([{"iid": 1}]).encode()


def config(provider: str) -> ProviderHTTPTransportConfig:
    return ProviderHTTPTransportConfig(
        api_base="https://gitlab.example" if provider == "gitlab" else "https://forgejo.example"
    )


def test_transport_is_get_only_and_projects_safe_headers():
    calls = []

    def opener(request, timeout):
        calls.append((request, timeout))
        return FakeResponse()

    transport = ProviderHTTPTransport("gitlab", token="secret-token", config=config("gitlab"), opener=opener)
    response = transport("/api/v4/projects/42/issues", {"page": "1"}, 2.5)
    request, timeout = calls[0]
    assert request.method == "GET"
    assert request.full_url == "https://gitlab.example/api/v4/projects/42/issues?page=1"
    assert request.get_header("User-agent") == DEFAULT_USER_AGENT
    assert request.get_header("Private-token") == "secret-token"
    assert timeout == 2.5
    assert response.headers == {
        "link": '<https://gitlab.example/api/v4/projects/42/issues?page=2>; rel="next"'
    }
    assert "secret-token" not in repr(transport)
    assert "secret-token" not in repr(response)


def test_forgejo_uses_explicit_authorization_header():
    seen = {}

    def opener(request, timeout):
        seen["request"] = request
        return FakeResponse()

    ProviderHTTPTransport("forgejo", token="secret", config=config("forgejo"), opener=opener)(
        "/api/v1/repos/acme/demo/issues", {}, 1
    )
    assert seen["request"].get_header("Authorization") == "token secret"


@pytest.mark.parametrize(
    ("provider", "path"),
    [
        ("gitlab", "/api/v4/projects/group%2Fproject/issues"),
        ("gitlab", "/api/v4/projects/42/issues?state=all"),
        ("forgejo", "/api/v1/repos/acme/../secret/issues"),
        ("forgejo", "/api/v1/repos/acme/demo/issues?state=open"),
    ],
)
def test_transport_rejects_non_allowlisted_paths(provider, path):
    transport = ProviderHTTPTransport(provider, config=config(provider), opener=lambda *_: FakeResponse())
    with pytest.raises(ProviderHTTPError, match="non-whitelisted"):
        transport(path, {}, 1)


def test_transport_requires_https_and_bounds_input():
    with pytest.raises(ProviderHTTPError, match="https"):
        ProviderHTTPTransport(
            "gitlab",
            config=ProviderHTTPTransportConfig(api_base="http://gitlab.example"),
        )
    with pytest.raises(ProviderHTTPError, match="https"):
        ProviderHTTPTransport("gitlab", config=ProviderHTTPTransportConfig(api_base="https://gitlab.example/"))
    with pytest.raises(ProviderHTTPError, match="single-line"):
        ProviderHTTPTransport("gitlab", token="bad\nsecret", config=config("gitlab"))
    with pytest.raises(ProviderHTTPError, match="single-line"):
        ProviderHTTPTransport("gitlab", config=ProviderHTTPTransportConfig(api_base="https://gitlab.example", user_agent="bad\tua"))
    with pytest.raises(ProviderHTTPError, match="max_response_bytes"):
        ProviderHTTPTransport("gitlab", config=ProviderHTTPTransportConfig(api_base="https://gitlab.example", max_response_bytes=1_000_001))


@pytest.mark.parametrize("timeout", [0, -1, 61, float("inf"), True])
def test_transport_rejects_invalid_timeout(timeout):
    transport = ProviderHTTPTransport("gitlab", config=config("gitlab"), opener=lambda *_: FakeResponse())
    with pytest.raises(ProviderHTTPError, match="timeout"):
        transport("/api/v4/projects/42/issues", {}, timeout)


def test_environment_token_requires_explicit_opt_in(monkeypatch):
    monkeypatch.setenv("GITLAB_TOKEN", "gitlab-secret")
    without_opt_in = ProviderHTTPTransport.from_environment("gitlab", config=config("gitlab"))
    assert without_opt_in.token is None
    with_opt_in = ProviderHTTPTransport.from_environment("gitlab", allow_environment=True, config=config("gitlab"))
    assert with_opt_in.token == "gitlab-secret"

    monkeypatch.setenv("FORGEJO_TOKEN", "forgejo-secret")
    forgejo = ProviderHTTPTransport.from_environment("forgejo", allow_environment=True, config=config("forgejo"))
    assert forgejo.token == "forgejo-secret"


def test_transport_redacts_network_errors_and_rejects_bad_responses():
    transport = ProviderHTTPTransport("gitlab", config=config("gitlab"), opener=lambda *_args, **_kwargs: (_ for _ in ()).throw(URLError("https://u:secret@example.invalid")))
    with pytest.raises(ProviderHTTPError, match="^HTTP request failed$") as raised:
        transport("/api/v4/projects/42/issues", {}, 1)
    assert "secret" not in str(raised.value)

    class BadResponse:
        status = 200
        headers = {}

        def read(self, limit):
            return "not-bytes"

    transport = ProviderHTTPTransport("gitlab", config=config("gitlab"), opener=lambda *_args, **_kwargs: BadResponse())
    with pytest.raises(ProviderHTTPError, match="body must be bytes"):
        transport("/api/v4/projects/42/issues", {}, 1)


def test_transport_bounds_response_reads_and_rejects_unknown_provider():
    class LargeResponse(FakeResponse):
        def read(self, limit):
            assert limit == 4
            return b"12345"

    transport = ProviderHTTPTransport(
        "gitlab",
        config=ProviderHTTPTransportConfig(api_base="https://gitlab.example", max_response_bytes=3),
        opener=lambda *_args, **_kwargs: LargeResponse(),
    )
    response = transport("/api/v4/projects/42/issues", {}, 1)
    assert response.body == b"1234"
    with pytest.raises(ProviderHTTPError, match="unsupported"):
        ProviderHTTPTransport("github", config=config("gitlab"))
