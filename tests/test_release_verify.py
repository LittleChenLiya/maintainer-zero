from pathlib import Path

import pytest

from tools.verify_release import DEFAULT_VERIFY_OUTPUT, verify


def test_release_verification_is_idempotent(tmp_path: Path):
    root = Path(__file__).parents[1]
    output = tmp_path / "release"

    verify(root, output)
    verify(root, output)

    assert len(list((output / "artifacts").glob("*.whl"))) == 1
    assert len(list((output / "artifacts").glob("*.tar.gz"))) == 1


def test_release_verification_default_output_is_an_absolute_codex_path():
    assert DEFAULT_VERIFY_OUTPUT.is_absolute()
    assert DEFAULT_VERIFY_OUTPUT == Path("D:/Codex/maintainer-zero-release-verify")


def test_release_verification_install_probe_is_offline_safe():
    source = (Path(__file__).parents[1] / "tools" / "verify_release.py").read_text(encoding="utf-8")
    assert "--no-build-isolation" in source, "release install must not resolve build dependencies from the network"


def test_release_verification_rejects_output_inside_source_checkout(tmp_path: Path):
    root = Path(__file__).parents[1]
    with pytest.raises(ValueError, match="outside the source checkout"):
        verify(root, root / "release-output")


def test_release_verification_rejects_symlinked_output_component(tmp_path: Path):
    root = Path(__file__).parents[1]
    outside = tmp_path / "outside"
    outside.mkdir()
    linked = tmp_path / "linked-output"
    try:
        linked.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")
    with pytest.raises(ValueError, match="may not contain a symlink"):
        verify(root, linked / "release")
