from pathlib import Path

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
