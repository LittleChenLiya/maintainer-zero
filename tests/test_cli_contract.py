from __future__ import annotations

import pytest

from maintainer_zero import __version__
from maintainer_zero.cli import _build_parser


def test_cli_version_is_available_without_a_subcommand(capsys: pytest.CaptureFixture[str]):
    with pytest.raises(SystemExit) as exc:
        _build_parser().parse_args(["--version"])

    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == f"maintainer-zero {__version__}"


def test_cli_still_requires_a_subcommand(capsys: pytest.CaptureFixture[str]):
    with pytest.raises(SystemExit) as exc:
        _build_parser().parse_args([])

    assert exc.value.code == 2
    assert "the following arguments are required: command" in capsys.readouterr().err
