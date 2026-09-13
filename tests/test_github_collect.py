import json

import pytest

from maintainer_zero.github_collect import (
    GitHubRepositoryError,
    collect_repository_metadata,
    repository_paths,
    validate_repository_slug,
)
from maintainer_zero.github_client import TransportResponse
from maintainer_zero.github_client import DEFAULT_MAX_RESPONSE_BYTES
from maintainer_zero.cli import main


def test_repository_slug_paths_are_bounded_and_deterministic():
    assert validate_repository_slug("acme/demo") == "acme/demo"
    assert repository_paths("acme/demo")["pull_requests"] == "/repos/acme/demo/pulls"
    assert repository_paths("acme/demo", reviews_pr=42)["reviews"] == "/repos/acme/demo/pulls/42/reviews"
    with pytest.raises(GitHubRepositoryError, match="OWNER/REPOSITORY"):
        validate_repository_slug("acme/demo/issues")
    with pytest.raises(GitHubRepositoryError, match="reviews_pr"):
        repository_paths("acme/demo", reviews_pr=0)


def test_collection_uses_read_only_resources_and_preserves_unknowns():
    calls = []

    def fetch(path, params, timeout):
        calls.append((path, dict(params), timeout))
        return TransportResponse(200, json.dumps([{"path": path}]), {})

    payload = collect_repository_metadata("acme/demo", fetch, page_size=2)
    assert sorted(payload["data"]) == ["issues", "pull_requests", "releases"]
    assert len(calls) == 3
    assert all(call[0].startswith("/repos/acme/demo/") for call in calls)
    assert all(call[2] == 5.0 for call in calls)
    assert payload["permissions"] == {"issues": True, "pull_requests": True, "releases": True}

def test_repository_metadata_is_opt_in_and_uses_single_object_request():
    calls = []

    def fetch(path, params, timeout):
        calls.append((path, dict(params)))
        if path.endswith("/issues") or path.endswith("/pulls") or path.endswith("/releases"):
            return TransportResponse(200, b"[]", {})
        return TransportResponse(200, json.dumps({"default_branch": "main", "visibility": "public", "archived": False}), {})

    payload = collect_repository_metadata("acme/demo", fetch, include_repository=True)
    assert payload["data"]["repository"]["default_branch"] == "main"
    assert next(params for path, params in calls if path == "/repos/acme/demo") == {}

def test_reviews_are_explicitly_scoped_to_one_pull_request():
    calls = []

    def fetch(path, params, timeout):
        calls.append(path)
        return TransportResponse(200, b"[]", {})

    payload = collect_repository_metadata("acme/demo", fetch, reviews_pr=7)
    assert "reviews" in payload["permissions"]
    assert "/repos/acme/demo/pulls/7/reviews" in calls


def test_cli_requires_explicit_network_opt_in(tmp_path, capsys):
    output = tmp_path / "github.json"
    assert main(["collect-github", "acme/demo", "--output", str(output)]) == 2
    assert "allow-network" in capsys.readouterr().out
    assert not output.exists()


def test_cli_success_path_writes_only_validated_snapshot(tmp_path, monkeypatch, capsys):
    seen = {}

    class FakeTransport:
        @classmethod
        def from_environment(cls, *, allow_environment=False):
            seen["allow_environment"] = allow_environment
            return cls()

        def __call__(self, path, params, timeout):
            return TransportResponse(200, json.dumps([{"path": path}]), {})

    monkeypatch.setattr("maintainer_zero.cli.GitHubHTTPTransport", FakeTransport)
    output = tmp_path / "nested" / "github.json"
    assert main([
        "collect-github", "acme/demo", "--allow-network",
        "--allow-environment-token", "--output", str(output),
    ]) == 0
    assert seen["allow_environment"] is True
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["permissions"] == {"issues": True, "pull_requests": True, "releases": True}
    assert "Collected read-only GitHub metadata" in capsys.readouterr().out

def test_cli_success_path_writes_atomic_snapshot_and_cache(tmp_path, monkeypatch):
    class FakeTransport:
        @classmethod
        def from_environment(cls, *, allow_environment=False):
            return cls()

        def __call__(self, path, params, timeout):
            return TransportResponse(200, json.dumps([{"path": path}]), {})

    monkeypatch.setattr("maintainer_zero.cli.GitHubHTTPTransport", FakeTransport)
    output = tmp_path / "snapshot.json"
    cache = tmp_path / "cache.json"
    assert main(["collect-github", "acme/demo", "--allow-network", "--output", str(output), "--cache-output", str(cache)]) == 0
    assert json.loads(output.read_text(encoding="utf-8"))["schema_version"] == 1
    assert json.loads(cache.read_text(encoding="utf-8"))["cache"]["source"] == "github-api"
    assert not list(tmp_path.glob(".snapshot.json.*.tmp"))

def test_cli_rejects_snapshot_cache_path_collision(tmp_path, monkeypatch):
    class FakeTransport:
        @classmethod
        def from_environment(cls, *, allow_environment=False):
            return cls()

        def __call__(self, path, params, timeout):
            return TransportResponse(200, b"[]", {})

    monkeypatch.setattr("maintainer_zero.cli.GitHubHTTPTransport", FakeTransport)
    output = tmp_path / "same.json"
    assert main(["collect-github", "acme/demo", "--allow-network", "--output", str(output), "--cache-output", str(output)]) == 2


def test_cli_rejects_symlinked_snapshot_output_parent(tmp_path, monkeypatch):
    class FakeTransport:
        @classmethod
        def from_environment(cls, *, allow_environment=False, **kwargs):
            return cls()

        def __call__(self, path, params, timeout):
            return TransportResponse(200, b"[]", {})

    monkeypatch.setattr("maintainer_zero.cli.GitHubHTTPTransport", FakeTransport)
    outside = tmp_path / "outside"
    outside.mkdir()
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")
    assert main(["collect-github", "acme/demo", "--allow-network", "--output", str(linked / "snapshot.json")]) == 2


def test_cli_rejects_unsafe_snapshot_output_before_transport(tmp_path, monkeypatch):
    outside = tmp_path / "outside"
    outside.mkdir()
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    called = False

    class UnexpectedTransport:
        @classmethod
        def from_environment(cls, **kwargs):
            nonlocal called
            called = True
            raise AssertionError("unsafe output must fail before transport construction")

    monkeypatch.setattr("maintainer_zero.cli.GitHubHTTPTransport", UnexpectedTransport)
    result = main([
        "collect-github", "acme/demo", "--allow-network",
        "--output", str(linked / "snapshot.json"),
    ])
    assert result == 2
    assert called is False


def test_cli_propagates_tighter_response_bound_to_transport_and_client(tmp_path, monkeypatch):
    seen = {}

    class FakeTransport:
        @classmethod
        def from_environment(cls, *, allow_environment=False, **kwargs):
            seen["allow_environment"] = allow_environment
            seen["config"] = kwargs.get("config")
            return cls()

        def __call__(self, path, params, timeout):
            return TransportResponse(200, b"[]", {})

    monkeypatch.setattr("maintainer_zero.cli.GitHubHTTPTransport", FakeTransport)
    output = tmp_path / "bounded.json"
    assert main([
        "collect-github", "acme/demo", "--allow-network",
        "--max-response-bytes", "4096", "--output", str(output),
    ]) == 0
    assert seen["config"].max_response_bytes == 4096


@pytest.mark.parametrize("value", ["0", "-1", str(DEFAULT_MAX_RESPONSE_BYTES + 1)])
def test_cli_rejects_invalid_response_bound(tmp_path, monkeypatch, value):
    class FakeTransport:
        @classmethod
        def from_environment(cls, *, allow_environment=False, **kwargs):
            return cls()

        def __call__(self, path, params, timeout):
            return TransportResponse(200, b"[]", {})

    monkeypatch.setattr("maintainer_zero.cli.GitHubHTTPTransport", FakeTransport)
    assert main([
        "collect-github", "acme/demo", "--allow-network",
        "--max-response-bytes", value, "--output", str(tmp_path / "invalid.json"),
    ]) == 2
