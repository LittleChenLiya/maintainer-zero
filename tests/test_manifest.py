from __future__ import annotations

import json
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
