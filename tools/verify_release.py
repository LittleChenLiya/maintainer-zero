"""Build and verify wheel/sdist artifacts outside the source checkout."""
from __future__ import annotations
import argparse, json, os, subprocess, sys, tempfile
import stat
from pathlib import Path

DEFAULT_VERIFY_OUTPUT = Path("D:/Codex/maintainer-zero-release-verify")
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_MAX_RELEASE_ARCHIVE_BYTES = 128 * 1024 * 1024

def run(command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(command, cwd=cwd, env=env, check=True, text=True, capture_output=True)
    return completed.stdout


def _is_link_or_reparse(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & _REPARSE_POINT)


def _safe_existing_directory(path: Path, label: str) -> Path:
    target = Path(os.path.abspath(path))
    try:
        info = target.lstat()
    except OSError as exc:
        raise ValueError(f"{label} is unavailable") from exc
    if _is_link_or_reparse(info):
        raise ValueError(f"{label} may not be a symlink or reparse point: {target}")
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError(f"{label} is not a directory: {target}")
    return target


def _safe_release_archives(wheelhouse: Path) -> list[Path]:
    """Return exactly one bounded, ordinary wheel and sdist archive."""
    _safe_existing_directory(wheelhouse, "release artifact directory")
    archives = sorted(wheelhouse.glob("*.whl")) + sorted(wheelhouse.glob("*.tar.gz"))
    if len(archives) != 2:
        raise RuntimeError(f"expected one wheel and one sdist, found {archives}")
    for archive in archives:
        try:
            info = archive.lstat()
        except OSError as exc:
            raise ValueError(f"release archive cannot be inspected: {archive}") from exc
        if _is_link_or_reparse(info) or not stat.S_ISREG(info.st_mode):
            raise ValueError(f"release archive target is unsafe: {archive}")
        if info.st_size <= 0 or info.st_size > _MAX_RELEASE_ARCHIVE_BYTES:
            raise ValueError(f"release archive has invalid size: {archive}")
    if not any(path.name.endswith(".whl") for path in archives) or not any(path.name.endswith(".tar.gz") for path in archives):
        raise RuntimeError(f"expected one wheel and one sdist, found {archives}")
    return archives


def _safe_output_directory(path: Path) -> Path:
    """Create an output directory without following symlinked components."""
    target = Path(os.path.abspath(path))
    current = Path(target.anchor) if target.anchor else Path()
    parts = target.parts[1:] if target.anchor else target.parts
    for part in parts:
        current /= part
        try:
            info = current.lstat()
        except FileNotFoundError:
            current.mkdir()
            info = current.lstat()
        if _is_link_or_reparse(info):
            raise ValueError(f"release verification output may not contain a symlink or reparse point: {current}")
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError(f"release verification output is not a directory: {current}")
    return target

def verify(root: Path, output: Path) -> None:
    root = root.resolve()
    output = Path(os.path.abspath(output))
    if output == root or output.is_relative_to(root):
        raise ValueError("release verification output must be outside the source checkout")
    output = _safe_output_directory(output)
    resolved_output = output.resolve()
    if resolved_output == root or resolved_output.is_relative_to(root):
        raise ValueError("release verification output must be outside the source checkout")
    wheelhouse = output / "artifacts"
    # The output directory is a tool-owned, disposable verification area.
    # Remove only files produced by this script so rerunning the documented
    # command cannot count stale archives or collide with old install targets.
    # Use lexists so a dangling symlink is treated as an existing unsafe
    # target rather than falling through to mkdir and leaking FileExistsError.
    if os.path.lexists(wheelhouse):
        _safe_existing_directory(wheelhouse, "release artifact directory")
        archives_to_remove = (*wheelhouse.glob("*.whl"), *wheelhouse.glob("*.tar.gz"))
        for archive in archives_to_remove:
            info = archive.lstat()
            if _is_link_or_reparse(info) or not stat.S_ISREG(info.st_mode):
                raise ValueError(f"release archive target is unsafe: {archive}")
            archive.unlink()
    else:
        wheelhouse.mkdir()
        _safe_existing_directory(wheelhouse, "release artifact directory")
    run([sys.executable, "-m", "pip", "wheel", str(root), "--no-deps", "--no-build-isolation", "--wheel-dir", str(wheelhouse)])
    build_sdist = "import setuptools.build_meta as b; b.build_sdist(%r)" % str(wheelhouse)
    run([sys.executable, "-c", build_sdist], cwd=root)
    archives = _safe_release_archives(wheelhouse)
    for archive in archives:
        # Keep install probes in a per-run temporary directory. This makes the
        # documented command repeatable without deleting arbitrary user files
        # below the caller-selected output directory.
        with tempfile.TemporaryDirectory(prefix="install-", dir=output) as target:
            run([sys.executable, "-m", "pip", "install", "--no-deps", "--no-build-isolation", "--target", target, str(archive)])
            env = os.environ.copy(); env["PYTHONPATH"] = target
            probe = "from pathlib import Path; import maintainer_zero; p=Path(maintainer_zero.__file__).resolve(); assert p.is_relative_to(Path(r'%s').resolve()); print(p)" % target
            run([sys.executable, "-c", probe], cwd=output, env=env)
            rendered = run([sys.executable, "-m", "maintainer_zero", "demo", "--format", "json", "--fail-on-regression"], cwd=output, env=env)
            payload = json.loads(rendered)
            if payload.get("schema_version") != 1 or len(payload.get("results", [])) != 3:
                raise RuntimeError(f"unexpected demo payload from {archive.name}")
    print(f"verified {len(archives)} artifacts outside source checkout: {output}")

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).parents[1])
    parser.add_argument("--output", type=Path, default=DEFAULT_VERIFY_OUTPUT)
    args = parser.parse_args(); verify(args.root.resolve(), args.output.resolve()); return 0

if __name__ == "__main__":
    raise SystemExit(main())
