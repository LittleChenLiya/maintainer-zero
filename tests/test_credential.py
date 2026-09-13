from __future__ import annotations
import json
from pathlib import Path
import pytest
from maintainer_zero.credential import CredentialError, create_credential, load_credential, verify_credential
from maintainer_zero.manifest import write_manifest
from maintainer_zero.cli import main

def fixture(root: Path):
    report = root / "continuity.json"
    report.write_text("{\"schema_version\": 1}\n", encoding="utf-8")
    md = root / "report.md"
    md.write_text("# report\n", encoding="utf-8")
    manifest = write_manifest(root, [report, md])
    return report, manifest

def test_credential_round_trip_is_offline_and_not_signature(tmp_path: Path):
    report, manifest = fixture(tmp_path)
    credential = create_credential(report, manifest)
    payload = load_credential(credential)
    assert "not-a-digital-signature" in payload["claims"]
    assert verify_credential(credential)["verified"] is True

@pytest.mark.parametrize("mutation", ["report", "manifest", "credential"])
def test_credential_detects_tampering(tmp_path: Path, mutation: str):
    report, manifest = fixture(tmp_path)
    credential = create_credential(report, manifest)
    if mutation == "report":
        report.write_text("changed\n", encoding="utf-8")
    elif mutation == "manifest":
        manifest.write_text(manifest.read_text(encoding="utf-8").replace("\"rule_version\": \"0.2\"", "\"rule_version\": \"changed\""), encoding="utf-8")
    else:
        payload = json.loads(credential.read_text(encoding="utf-8"))
        payload["content_digest"]["value"] = "0" * 64
        credential.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CredentialError):
        verify_credential(credential)

def test_credential_rejects_duplicate_keys(tmp_path: Path):
    report, manifest = fixture(tmp_path)
    credential = create_credential(report, manifest)
    raw = credential.read_text(encoding="utf-8").replace("\"schema_version\": 1,", "\"schema_version\": 1, \"schema_version\": 1,")
    credential.write_text(raw, encoding="utf-8")
    with pytest.raises(CredentialError, match="duplicate"):
        load_credential(credential)

def test_verify_credential_cli_exit_codes(tmp_path: Path, capsys):
    report, manifest = fixture(tmp_path)
    credential = create_credential(report, manifest)
    assert main(["verify-credential", str(credential), "--format", "json"]) == 0
    assert "\"verified\": true" in capsys.readouterr().out
    report.write_text("tampered\n", encoding="utf-8")
    assert main(["verify-credential", str(credential)]) == 2
    assert "error:" in capsys.readouterr().out

def test_credential_rejects_control_and_windows_paths(tmp_path: Path):
    report, manifest = fixture(tmp_path)
    credential = create_credential(report, manifest)
    payload = json.loads(credential.read_text(encoding="utf-8"))
    for item in (payload["report"], payload["manifest"]):
        item["path"] = "C:/outside.json"
        with pytest.raises(CredentialError, match="normalized"):
            credential.write_text(json.dumps(payload), encoding="utf-8")
            load_credential(credential)
        item["path"] = "report.json" if item is payload["report"] else "artifact-manifest.json"
    credential.write_text(json.dumps(payload), encoding="utf-8")

def test_create_credential_rejects_output_collision(tmp_path: Path):
    report, manifest = fixture(tmp_path)
    with pytest.raises(CredentialError, match="must not replace"):
        create_credential(report, manifest, report)
    with pytest.raises(CredentialError, match="must not replace"):
        create_credential(report, manifest, manifest)

def test_credential_rejects_symlink_parent(tmp_path: Path):
    report, manifest = fixture(tmp_path)
    credential = create_credential(report, manifest)
    outside = tmp_path / "outside"; outside.mkdir()
    linked = tmp_path / "linked"
    try: linked.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError): pytest.skip("symlinks unavailable")
    moved = linked / credential.name
    credential.unlink()
    with pytest.raises(CredentialError, match="parent"):
        load_credential(moved)
