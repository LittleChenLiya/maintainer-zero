import json
from datetime import datetime, timezone, timedelta
import pytest
from maintainer_zero.github_cache import (
    MetadataCacheError, cache_status, load_metadata_cache, save_metadata_cache,
)


def payload():
    return {"schema_version": 1, "permissions": {"issues": True}, "data": {"issues": [{"number": 1}]}}


def test_save_and_load_cache_is_bounded_and_deterministic(tmp_path):
    path = tmp_path / "cache.json"
    fetched = datetime(2026, 1, 1, tzinfo=timezone.utc)
    saved = save_metadata_cache(path, payload(), source="github-api", ttl_seconds=3600, fetched_at=fetched)
    assert saved["cache"]["expires_at"] == "2026-01-01T01:00:00Z"
    assert load_metadata_cache(path, now=fetched)["cache"]["source"] == "github-api"
    assert cache_status(path, now=fetched).as_dict()["state"] == "fresh"


def test_stale_cache_requires_explicit_opt_in(tmp_path):
    path = tmp_path / "cache.json"
    fetched = datetime(2026, 1, 1, tzinfo=timezone.utc)
    save_metadata_cache(path, payload(), fetched_at=fetched, ttl_seconds=60)
    status = cache_status(path, now=fetched + timedelta(seconds=60))
    assert status.state == "stale"
    assert status.reason == "expired"
    with pytest.raises(MetadataCacheError, match="stale"):
        load_metadata_cache(path, now=fetched + timedelta(seconds=60))
    assert load_metadata_cache(path, now=fetched + timedelta(seconds=60), allow_stale=True)["cache"]


@pytest.mark.parametrize("kwargs", [
    {"ttl_seconds": 0}, {"ttl_seconds": 30 * 24 * 60 * 60 + 1},
    {"source": "../token"}, {"source": ""},
])
def test_cache_bounds_are_rejected(tmp_path, kwargs):
    with pytest.raises(MetadataCacheError):
        save_metadata_cache(tmp_path / "cache.json", payload(), fetched_at=datetime.now(timezone.utc), **kwargs)


def test_cache_rejects_tampered_expiry_and_missing_file(tmp_path):
    path = tmp_path / "cache.json"
    save_metadata_cache(path, payload(), fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc), ttl_seconds=60)
    altered = json.loads(path.read_text())
    altered["cache"]["expires_at"] = "2026-01-01T00:00:01Z"
    path.write_text(json.dumps(altered))
    assert cache_status(path).state == "invalid"
    with pytest.raises(MetadataCacheError, match="expires_at"):
        load_metadata_cache(path)
    assert cache_status(tmp_path / "missing.json").state == "missing"


def test_cache_write_failure_preserves_existing_file_and_cleans_temp(tmp_path, monkeypatch):
    path = tmp_path / "cache.json"
    save_metadata_cache(path, payload(), fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc), ttl_seconds=60)
    original = path.read_bytes()

    def fail_replace(source, target):
        raise OSError("simulated replace failure")

    monkeypatch.setattr("maintainer_zero.github_cache.os.replace", fail_replace)
    with pytest.raises(MetadataCacheError, match="could not write"):
        save_metadata_cache(path, payload(), fetched_at=datetime(2026, 1, 2, tzinfo=timezone.utc), ttl_seconds=60)
    assert path.read_bytes() == original
    assert not list(tmp_path.glob(".cache.json.*.tmp"))


def test_cache_read_converts_deep_json_recursion_to_cache_error(tmp_path):
    nested = "[" * 70 + "0" + "]" * 70
    path = tmp_path / "deep-cache.json"
    path.write_text(
        '{"schema_version":1,"permissions":{"issues":true},'
        f'"data":{{"issues":[{{"nested":{nested}}}]}}}}',
        encoding="utf-8",
    )
    with pytest.raises(MetadataCacheError, match="payload is invalid"):
        load_metadata_cache(path)


def test_cache_rejects_credential_like_top_level_fields(tmp_path):
    unsafe = dict(payload(), token="do-not-store", secret="also-do-not-store")
    with pytest.raises(MetadataCacheError, match="payload is invalid"):
        save_metadata_cache(tmp_path / "unsafe.json", unsafe)
