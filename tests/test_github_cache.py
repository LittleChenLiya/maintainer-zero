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

