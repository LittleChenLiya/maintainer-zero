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


def test_simulate_parser_accepts_data_only_fallback_plan():
    args = _build_parser().parse_args(["simulate", ".", "--fallback-plan", "fallback.json"])
    assert args.fallback_plan == "fallback.json"


def test_validate_fallback_plan_parser_is_read_only():
    args = _build_parser().parse_args(["validate-fallback-plan", "fallback.json", "--format", "json"])
    assert args.command == "validate-fallback-plan"
    assert args.fallback_format == "json"


def test_validate_metadata_parser_is_read_only():
    args = _build_parser().parse_args(["validate-metadata", "metadata.json", "--format", "json"])
    assert args.command == "validate-metadata"
    assert args.metadata_format == "json"


def test_export_benchmark_parser_requires_output():
    args = _build_parser().parse_args(["export-benchmark", "report.json", "--output", "benchmark.json"])
    assert args.command == "export-benchmark"
    assert args.benchmark_format == "json"


def test_validate_benchmark_parser_is_read_only():
    args = _build_parser().parse_args(["validate-benchmark", "benchmark.json", "--format", "json"])
    assert args.command == "validate-benchmark"
    assert args.benchmark_validate_format == "json"


def test_validate_report_parser_is_read_only():
    args = _build_parser().parse_args(["validate-report", "continuity.json", "--format", "json"])
    assert args.command == "validate-report"
    assert args.report_validate_format == "json"

def test_verify_credential_parser_is_read_only():
    args = _build_parser().parse_args(["verify-credential", "credential.json", "--format", "json"])
    assert args.command == "verify-credential"
    assert args.credential_format == "json"

def test_create_credential_parser_accepts_report_manifest_and_output():
    args = _build_parser().parse_args(["create-credential", "report.json", "manifest.json", "--output", "credential.json"])
    assert args.command == "create-credential"
    assert args.output == "credential.json"
