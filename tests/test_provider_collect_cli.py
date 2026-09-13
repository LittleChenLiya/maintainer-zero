from __future__ import annotations

import json

import pytest

from maintainer_zero.cli import _build_parser, main
from maintainer_zero.github_client import TransportResponse


def test_collect_provider_parser_exposes_bounded_read_only_options():
    args = _build_parser().parse_args(
        [
            "collect-provider",
            "forgejo",
            "acme/demo",
            "--api-base",
            "https://forgejo.example",
            "--allow-network",
            "--allow-environment-token",
            "--timeout",
            "2.5",
            "--max-pages",
            "3",
            "--page-size",
            "25",
            "--max-response-bytes",
            "4096",
            "--reviews-pr",
            "7",
            "--include-repository",
            "--cache-output",
            "cache.json",
            "--cache-ttl",
            "60",
        ]
    )
    assert args.command == "collect-provider"
    assert args.provider == "forgejo"
    assert args.identifier == "acme/demo"
    assert args.allow_network is True
    assert args.allow_environment_token is True
    assert args.timeout == 2.5
    assert args.max_pages == 3
    assert args.page_size == 25
    assert args.max_response_bytes == 4096
    assert args.reviews_pr == 7
    assert args.include_repository is True
    assert args.cache_ttl == 60


def test_collect_provider_requires_explicit_network_opt_in(tmp_path, monkeypatch, capsys):
    output = tmp_path / "metadata.json"
    called = False

    class UnexpectedTransport:
        @classmethod
        def from_environment(cls, *args, **kwargs):
            nonlocal called
            called = True
            return cls()

    monkeypatch.setattr("maintainer_zero.cli.ProviderHTTPTransport", UnexpectedTransport)
    assert main(
        [
            "collect-provider",
            "gitlab",
            "42",
            "--api-base",
            "https://gitlab.example",
            "--output",
            str(output),
        ]
    ) == 2
    assert called is False
    assert not output.exists()
    assert "--allow-network" in capsys.readouterr().out


def test_collect_provider_success_wires_transport_bounds_and_writes_cache(
    tmp_path, monkeypatch, capsys
):
    seen: dict[str, object] = {}

    class FakeTransport:
        @classmethod
        def from_environment(cls, provider, *, allow_environment=False, config):
            seen["provider"] = provider
            seen["allow_environment"] = allow_environment
            seen["config"] = config
            return cls()

        def __call__(self, path, params, timeout):
            seen.setdefault("calls", []).append((path, dict(params), timeout))
            return TransportResponse(200, b"[]", {})

    monkeypatch.setattr("maintainer_zero.cli.ProviderHTTPTransport", FakeTransport)
    output = tmp_path / "nested" / "forgejo.json"
    cache = tmp_path / "nested" / "forgejo-cache.json"
    result = main(
        [
            "collect-provider",
            "forgejo",
            "acme/demo",
            "--api-base",
            "https://forgejo.example",
            "--allow-network",
            "--allow-environment-token",
            "--timeout",
            "2.5",
            "--max-pages",
            "2",
            "--page-size",
            "10",
            "--max-response-bytes",
            "4096",
            "--reviews-pr",
            "7",
            "--output",
            str(output),
            "--cache-output",
            str(cache),
            "--cache-ttl",
            "60",
        ]
    )
    assert result == 0
    assert seen["provider"] == "forgejo"
    assert seen["allow_environment"] is True
    assert seen["config"].api_base == "https://forgejo.example"
    assert seen["config"].max_response_bytes == 4096
    assert len(seen["calls"]) == 4
    assert any(path.endswith("/pulls/7/reviews") for path, _, _ in seen["calls"])
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["provider"] == "forgejo"
    assert payload["permissions"] == {
        "issues": True,
        "pull_requests": True,
        "releases": True,
        "reviews": True,
    }
    cached = json.loads(cache.read_text(encoding="utf-8"))
    assert cached["cache"]["source"] == "forgejo-api"
    assert "Collected read-only forgejo metadata" in capsys.readouterr().out
    assert not list(output.parent.glob(".*.tmp"))


def test_collect_provider_rejects_gitlab_reviews_before_writing(tmp_path, monkeypatch):
    class UnexpectedTransport:
        @classmethod
        def from_environment(cls, *args, **kwargs):
            return lambda *args, **kwargs: TransportResponse(200, b"[]", {})

    monkeypatch.setattr("maintainer_zero.cli.ProviderHTTPTransport", UnexpectedTransport)
    output = tmp_path / "gitlab.json"
    assert main(
        [
            "collect-provider",
            "gitlab",
            "42",
            "--api-base",
            "https://gitlab.example",
            "--allow-network",
            "--reviews-pr",
            "1",
            "--output",
            str(output),
        ]
    ) == 2
    assert not output.exists()


@pytest.mark.parametrize(
    "api_base",
    [
        "http://gitlab.example",
        "https://gitlab.example/",
        "https://user:secret@gitlab.example",
        "https://gitlab.example?token=secret",
    ],
)
def test_collect_provider_rejects_unsafe_api_base_without_output(
    tmp_path, api_base
):
    output = tmp_path / "metadata.json"
    assert main(
        [
            "collect-provider",
            "gitlab",
            "42",
            "--api-base",
            api_base,
            "--allow-network",
            "--output",
            str(output),
        ]
    ) == 2
    assert not output.exists()


def test_collect_provider_rejects_control_character_api_base_before_transport(
    tmp_path, monkeypatch
):
    called = False

    class UnexpectedTransport:
        @classmethod
        def from_environment(cls, *args, **kwargs):
            nonlocal called
            called = True
            raise AssertionError("unsafe API base must fail before transport construction")

    monkeypatch.setattr("maintainer_zero.cli.ProviderHTTPTransport", UnexpectedTransport)
    output = tmp_path / "metadata.json"
    assert main(
        [
            "collect-provider",
            "forgejo",
            "acme/demo",
            "--api-base",
            "https://forgejo.example/\x1f",
            "--allow-network",
            "--output",
            str(output),
        ]
    ) == 2
    assert called is False
    assert not output.exists()


def test_collect_provider_rejects_unsafe_output_before_transport(tmp_path, monkeypatch):
    outside = tmp_path / "outside"
    outside.mkdir()
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")
    called = False

    class UnexpectedTransport:
        @classmethod
        def from_environment(cls, *args, **kwargs):
            nonlocal called
            called = True
            raise AssertionError("unsafe output must fail before transport construction")

    monkeypatch.setattr("maintainer_zero.cli.ProviderHTTPTransport", UnexpectedTransport)
    assert main(
        [
            "collect-provider",
            "gitlab",
            "42",
            "--api-base",
            "https://gitlab.example",
            "--allow-network",
            "--output",
            str(linked / "metadata.json"),
        ]
    ) == 2
    assert called is False


def test_collect_provider_rejects_output_cache_collision(tmp_path, monkeypatch):
    class FakeTransport:
        @classmethod
        def from_environment(cls, *args, **kwargs):
            return cls()

        def __call__(self, path, params, timeout):
            return TransportResponse(200, b"[]", {})

    monkeypatch.setattr("maintainer_zero.cli.ProviderHTTPTransport", FakeTransport)
    output = tmp_path / "same.json"
    assert main(
        [
            "collect-provider",
            "forgejo",
            "acme/demo",
            "--api-base",
            "https://forgejo.example",
            "--allow-network",
            "--output",
            str(output),
            "--cache-output",
            str(output),
        ]
    ) == 2
    assert not output.exists()
