from __future__ import annotations

import json
from urllib.parse import parse_qs, urlsplit

from maintainer_zero.cli import main
from maintainer_zero.github_cache import load_metadata_cache, save_metadata_cache
from maintainer_zero.github_metadata import summarize_metadata
from maintainer_zero.metadata_provider import ReadOnlyProviderClient
from maintainer_zero.provider_http import ProviderHTTPTransport, ProviderHTTPTransportConfig


def test_gitlab_transport_client_cache_and_validation_form_one_offline_flow(tmp_path, capsys):
    requests = []

    def opener(request, timeout):
        requests.append((request, timeout))
        path = urlsplit(request.full_url).path
        query = parse_qs(urlsplit(request.full_url).query)
        assert request.method == "GET"
        assert timeout == 3.0
        if path.endswith("/projects/42"):
            body = {
                "default_branch": "main",
                "visibility": "public",
                "owner": {"username": "private"},
                "web_url": "https://gitlab.example/acme/demo",
            }
        elif path.endswith("/issues"):
            assert query == {"page": ["1"], "per_page": ["25"]}
            body = [{"iid": 9, "state": "opened", "author": {"username": "private"}}]
        elif path.endswith("/merge_requests"):
            assert query == {"page": ["1"], "per_page": ["25"]}
            body = []
        elif path.endswith("/releases"):
            assert query == {"page": ["1"], "per_page": ["25"]}
            body = []
        else:  # pragma: no cover - the allowlisted client should never reach this
            raise AssertionError(path)
        return type("Response", (), {"status": 200, "headers": {}, "read": lambda self, limit: json.dumps(body).encode()})()

    transport = ProviderHTTPTransport(
        "gitlab",
        config=ProviderHTTPTransportConfig(api_base="https://gitlab.example"),
        opener=opener,
    )
    client = ReadOnlyProviderClient(
        "gitlab", transport, timeout_seconds=3.0, page_size=25
    )
    payload = client.collect("42", include_repository=True)

    assert payload["provider"] == "gitlab"
    assert payload["data"]["repository"] == {"default_branch": "main", "visibility": "public"}
    assert payload["data"]["issues"] == [{"number": 9, "state": "opened"}]
    serialized = json.dumps(payload)
    assert "private" not in serialized
    assert "web_url" not in serialized
    assert len(requests) == 4

    cache = tmp_path / "gitlab-cache.json"
    save_metadata_cache(cache, payload, source="gitlab-api", ttl_seconds=3600)
    cached = load_metadata_cache(cache)
    assert summarize_metadata(cached)["provider"] == "gitlab"
    assert main(["validate-metadata", str(cache), "--format", "json"]) == 0
    assert "gitlab" in capsys.readouterr().out
