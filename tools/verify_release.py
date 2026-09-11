"""Build and verify wheel/sdist artifacts outside the source checkout."""
from __future__ import annotations
import argparse, json, os, subprocess, sys, tempfile
from pathlib import Path

def run(command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(command, cwd=cwd, env=env, check=True, text=True, capture_output=True)
    return completed.stdout

def verify(root: Path, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    wheelhouse = output / "artifacts"
    # The output directory is a tool-owned, disposable verification area.
    # Remove only files produced by this script so rerunning the documented
    # command cannot count stale archives or collide with old install targets.
    if wheelhouse.exists():
        for archive in (*wheelhouse.glob("*.whl"), *wheelhouse.glob("*.tar.gz")):
            archive.unlink()
    else:
        wheelhouse.mkdir()
    run([sys.executable, "-m", "pip", "wheel", str(root), "--no-deps", "--no-build-isolation", "--wheel-dir", str(wheelhouse)])
    build_sdist = "import setuptools.build_meta as b; b.build_sdist(%r)" % str(wheelhouse)
    run([sys.executable, "-c", build_sdist], cwd=root)
    archives = sorted(wheelhouse.glob("*.whl")) + sorted(wheelhouse.glob("*.tar.gz"))
    if len(archives) != 2:
        raise RuntimeError(f"expected one wheel and one sdist, found {archives}")
    for archive in archives:
        # Keep install probes in a per-run temporary directory. This makes the
        # documented command repeatable without deleting arbitrary user files
        # below the caller-selected output directory.
        with tempfile.TemporaryDirectory(prefix="install-", dir=output) as target:
            run([sys.executable, "-m", "pip", "install", "--no-deps", "--target", target, str(archive)])
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
    parser.add_argument("--output", type=Path, default=Path(r"D:\\Codex\\maintainer-zero-release-verify"))
    args = parser.parse_args(); verify(args.root.resolve(), args.output.resolve()); return 0

if __name__ == "__main__":
    raise SystemExit(main())
