from __future__ import annotations

import json
from types import SimpleNamespace
from pathlib import Path

import pytest

from maintainer_zero.cli import main
from maintainer_zero.manifest import ManifestError, load_manifest, verify_manifest, write_manifest


def _artifacts(root: Path) -> list[Path]:
    (root / "continuity.json").write_text('{"ok": true}\n', encoding="utf-8")
    (root / "report.md").write_text("# report\n", encoding="utf-8")
    (root / "recovery").mkdir()
    (root / "recovery" / "runbook.md").write_text("draft\n", encoding="utf-8")
    return [root / "continuity.json", root / "report.md", root / "recovery" / "runbook.md"]


def test_manifest_round_trip_is_local_and_excludes_itself(tmp_path: Path):
    artifacts = _artifacts(tmp_path)
    manifest = write_manifest(tmp_path, artifacts)
    payload = load_manifest(manifest)
    assert {item["path"] for item in payload["artifacts"]} == {"continuity.json", "report.md", "recovery/runbook.md"}
    assert verify_manifest(manifest)["verified"] == 3
    assert all("\\" not in item["path"] for item in payload["artifacts"])


@pytest.mark.parametrize("mutation", ["content", "size"])
def test_manifest_detects_tampering(tmp_path: Path, mutation: str):
    artifacts = _artifacts(tmp_path)
    manifest = write_manifest(tmp_path, artifacts)
    target = tmp_path / "report.md"
    target.write_text("# changed\n" if mutation == "content" else "# report\nextra\n", encoding="utf-8")
    with pytest.raises(ManifestError):
        verify_manifest(manifest)


def test_manifest_rejects_missing_artifact_and_extra_fields(tmp_path: Path):
    artifacts = _artifacts(tmp_path)
    manifest = write_manifest(tmp_path, artifacts)
    (tmp_path / "report.md").unlink()
    with pytest.raises(ManifestError, match="missing"):
        verify_manifest(manifest)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["unexpected"] = True
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ManifestError, match="invalid"):
        load_manifest(manifest)


def test_manifest_rejects_descriptor_redirect_before_hashing(tmp_path: Path, monkeypatch):
    """A path replacement between lstat/open must fail closed."""
    artifacts = _artifacts(tmp_path)
    manifest = write_manifest(tmp_path, artifacts)
    target = tmp_path / "report.md"
    expected = target.lstat()
    original_fstat = __import__("os").fstat

    def mismatched_fstat(fd):
        info = original_fstat(fd)
        return SimpleNamespace(
            st_mode=info.st_mode,
            st_file_attributes=getattr(info, "st_file_attributes", 0),
            st_dev=info.st_dev,
            st_ino=expected.st_ino + 1,
            st_size=info.st_size,
            st_mtime_ns=info.st_mtime_ns,
        )

    monkeypatch.setattr("maintainer_zero.manifest.os.fstat", mismatched_fstat)
    with pytest.raises(ManifestError, match="changed before"):
        verify_manifest(manifest)


@pytest.mark.parametrize("artifact", [
    "missing.txt",
    "../outside.txt",
    "bad\\name.txt",
])
def test_manifest_writer_rejects_invalid_artifact_instead_of_dropping_it(tmp_path: Path, artifact: str):
    _artifacts(tmp_path)
    with pytest.raises(ManifestError):
        write_manifest(tmp_path, [tmp_path / "report.md", artifact])


def test_manifest_writer_rejects_artifact_outside_root(tmp_path: Path):
    _artifacts(tmp_path)
    outside = tmp_path.parent / "outside-artifact.txt"
    outside.write_text("outside\n", encoding="utf-8")
    with pytest.raises(ManifestError):
        write_manifest(tmp_path, [tmp_path / "report.md", outside])


def test_manifest_writer_rejects_casefold_duplicate_instead_of_dropping_one(tmp_path: Path):
    _artifacts(tmp_path)
    upper = tmp_path / "Report.md"
    upper.write_text("other report\n", encoding="utf-8")
    with pytest.raises(ManifestError, match="duplicate"):
        write_manifest(tmp_path, [tmp_path / "report.md", upper])


def test_manifest_writer_wraps_non_path_items_as_manifest_error(tmp_path: Path):
    _artifacts(tmp_path)
    with pytest.raises(ManifestError, match="filesystem path"):
        write_manifest(tmp_path, [tmp_path / "report.md", None])


@pytest.mark.parametrize("path", ["/absolute.txt", "../escape.txt", "recovery/../escape.txt"])
def test_manifest_rejects_unsafe_paths(tmp_path: Path, path: str):
    _artifacts(tmp_path)
    payload = {"schema_version": 1, "tool": {"name": "Maintainer-Zero", "version": "0.2.0"}, "rule_version": "0.2", "artifacts": [{"path": path, "size": 0, "sha256": "0" * 64}]}
    manifest = tmp_path / "artifact-manifest.json"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ManifestError):
        load_manifest(manifest)


def test_verify_manifest_cli_exit_codes(tmp_path: Path, capsys):
    manifest = write_manifest(tmp_path, _artifacts(tmp_path))
    assert main(["verify-manifest", str(manifest), "--format", "json"]) == 0
    assert '"verified": 3' in capsys.readouterr().out
    (tmp_path / "report.md").write_text("tampered\n", encoding="utf-8")
    assert main(["verify-manifest", str(manifest)]) == 2
    assert "error:" in capsys.readouterr().out


def test_simulate_writes_manifest_even_when_score_gate_fails(tmp_path: Path):
    repo = Path(__file__).parent / "fixtures" / "e2e-repository"
    output = tmp_path / "output"
    assert main(["simulate", str(repo), "--days", "7", "--output", str(output), "--fail-under", "100"]) == 1
    assert (output / "artifact-manifest.json").exists()
    assert verify_manifest(output / "artifact-manifest.json")["verified"] == 7
