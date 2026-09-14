"""Build and verify wheel/sdist artifacts outside the source checkout."""
from __future__ import annotations
import argparse, hashlib, json, os, subprocess, sys, tempfile
import stat
from pathlib import Path

DEFAULT_VERIFY_OUTPUT = Path("D:/Codex/maintainer-zero-release-verify")
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_MAX_RELEASE_ARCHIVE_BYTES = 128 * 1024 * 1024
_RELEASE_CHUNK = 1024 * 1024
_SOURCE_SKIP_DIRS = {".git", ".hg", ".svn", ".pytest_cache", "__pycache__", "build", "dist"}

def run(command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(command, cwd=cwd, env=env, check=True, text=True, capture_output=True)
    return completed.stdout


def _is_link_or_reparse(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & _REPARSE_POINT)


def _safe_existing_directory(path: Path, label: str) -> Path:
    target = Path(path)
    if not target.is_absolute():
        target = Path.cwd() / target
    current = Path(target.anchor) if target.anchor else Path()
    parts = target.parts[1:] if target.anchor else target.parts
    for part in parts:
        current /= part
        try:
            info = current.lstat()
        except OSError as exc:
            raise ValueError(f"{label} is unavailable") from exc
        if _is_link_or_reparse(info):
            raise ValueError(f"{label} may not be a symlink or reparse point: {current}")
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError(f"{label} is not a directory: {current}")
    return Path(os.path.normpath(os.fspath(target)))


def _same_source_stat(left: os.stat_result, right: os.stat_result) -> bool:
    """Compare the source identity and metadata used by snapshot races."""
    return (
        (getattr(left, "st_dev", -1), getattr(left, "st_ino", -1))
        == (getattr(right, "st_dev", -1), getattr(right, "st_ino", -1))
        and left.st_mode == right.st_mode
        and left.st_size == right.st_size
        and left.st_mtime_ns == right.st_mtime_ns
    )


def _copy_release_source(root: Path, target: Path) -> None:
    """Copy packaging inputs to an isolated, link-free source snapshot."""
    root = _safe_existing_directory(root, "release source checkout")
    target = _safe_existing_directory(target, "release source snapshot")
    try:
        root_info = root.lstat()
    except OSError as exc:
        raise ValueError(f"cannot inspect release source: {root}") from exc

    def copy_entry(source: Path, destination: Path) -> None:
        try:
            source.resolve(strict=False).relative_to(root)
        except (OSError, RuntimeError, ValueError) as exc:
            raise ValueError(f"release source entry escapes checkout: {source}") from exc
        try:
            info = source.lstat()
        except OSError as exc:
            raise ValueError(f"cannot inspect release source: {source}") from exc
        if _is_link_or_reparse(info):
            raise ValueError(f"release source may not contain a symlink or reparse point: {source}")
        if stat.S_ISDIR(info.st_mode):
            destination.mkdir()
            try:
                children = sorted(source.iterdir(), key=lambda item: item.name.casefold())
            except OSError as exc:
                raise ValueError(f"cannot enumerate release source: {source}") from exc
            for child in children:
                if child.name in _SOURCE_SKIP_DIRS or child.name.startswith(".continuity") or child.name.startswith(".release") or child.name.endswith(".egg-info"):
                    continue
                copy_entry(child, destination / child.name)
            try:
                finished = source.lstat()
            except OSError as exc:
                raise ValueError(f"release source changed during snapshot: {source}") from exc
            if not _same_source_stat(info, finished) or _is_link_or_reparse(finished):
                raise ValueError(f"release source changed during snapshot: {source}")
            return
        if not stat.S_ISREG(info.st_mode):
            raise ValueError(f"release source contains a special file: {source}")
        temporary: Path | None = None
        try:
            # Open through a descriptor and recheck its identity before and
            # after copying. O_NOFOLLOW (where available) also closes the
            # final-component symlink race between lstat and open.
            descriptor = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            try:
                opened = os.fstat(descriptor)
                if _is_link_or_reparse(opened) or not stat.S_ISREG(opened.st_mode) or not _same_source_stat(info, opened):
                    raise ValueError(f"release source changed before snapshot: {source}")
                with os.fdopen(descriptor, "rb") as source_handle:
                    descriptor = -1
                    with tempfile.NamedTemporaryFile(mode="wb", dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp", delete=False) as destination_handle:
                        temporary = Path(destination_handle.name)
                        while True:
                            chunk = source_handle.read(_RELEASE_CHUNK)
                            if not chunk:
                                break
                            destination_handle.write(chunk)
                        # Preserve POSIX executable/read-only bits from the
                        # checkout. A plain temporary-file create defaults to
                        # the process umask, which can silently change the
                        # behavior of packaged scripts and sdist metadata.
                        mode = stat.S_IMODE(info.st_mode)
                        # Prefer descriptor-based chmod where available so a
                        # replacement of the random temporary pathname cannot
                        # redirect the permission update. Windows does not
                        # expose ``fchmod``; its path-based fallback remains
                        # limited to the private temporary file.
                        if hasattr(os, "fchmod"):
                            os.fchmod(destination_handle.fileno(), mode)
                        else:
                            os.chmod(temporary, mode)
                        destination_handle.flush()
                        os.fsync(destination_handle.fileno())
                        # ``copy2`` used by the former implementation retained
                        # timestamps. Keep that packaging-visible metadata while
                        # the temporary pathname is still private, so generated
                        # sdists do not vary solely because of snapshot timing.
                        # Some Windows Python builds expose ``follow_symlinks``
                        # but raise ``NotImplementedError`` for ``utime``. The
                        # temporary file is still held open here; on that
                        # platform-specific fallback, verify its identity again
                        # before publishing it with ``os.replace``.
                        temporary_info = os.fstat(destination_handle.fileno())
                        try:
                            os.utime(temporary, ns=(info.st_atime_ns, info.st_mtime_ns), follow_symlinks=False)
                        except NotImplementedError:
                            os.utime(temporary, ns=(info.st_atime_ns, info.st_mtime_ns))
                        temporary_after_times = os.fstat(destination_handle.fileno())
                        if (
                            (temporary_info.st_dev, temporary_info.st_ino)
                            != (temporary_after_times.st_dev, temporary_after_times.st_ino)
                            or temporary_info.st_mode != temporary_after_times.st_mode
                            or temporary_info.st_size != temporary_after_times.st_size
                        ):
                            raise ValueError(f"release snapshot temporary changed during timestamp update: {source}")
                        try:
                            temporary_path_info = temporary.lstat()
                        except OSError as exc:
                            raise ValueError(f"release snapshot temporary disappeared during timestamp update: {source}") from exc
                        if (
                            (temporary_path_info.st_dev, temporary_path_info.st_ino)
                            != (temporary_after_times.st_dev, temporary_after_times.st_ino)
                            or _is_link_or_reparse(temporary_path_info)
                            or not stat.S_ISREG(temporary_path_info.st_mode)
                        ):
                            raise ValueError(f"release snapshot temporary redirected during timestamp update: {source}")
                        finished = os.fstat(source_handle.fileno())
            finally:
                if descriptor != -1:
                    os.close(descriptor)
            current = source.lstat()
            if not _same_source_stat(info, finished) or not _same_source_stat(info, current):
                raise ValueError(f"release source changed during snapshot: {source}")
            os.replace(temporary, destination)
            temporary = None
        except OSError as exc:
            raise ValueError(f"cannot snapshot release source: {source}") from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    try:
        entries = sorted(root.iterdir(), key=lambda item: item.name.casefold())
    except OSError as exc:
        raise ValueError(f"cannot enumerate release source: {root}") from exc
    for entry in entries:
        if entry.name in _SOURCE_SKIP_DIRS or entry.name.startswith(".continuity") or entry.name.startswith(".release") or entry.name.endswith(".egg-info"):
            continue
        copy_entry(entry, target / entry.name)
    try:
        finished_root = root.lstat()
    except OSError as exc:
        raise ValueError(f"release source changed during snapshot: {root}") from exc
    if not _same_source_stat(root_info, finished_root) or _is_link_or_reparse(finished_root):
        raise ValueError(f"release source changed during snapshot: {root}")


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


def _digest_release_file(path: Path, expected: os.stat_result) -> tuple[int, str]:
    """Hash a release file through a stable descriptor and pathname."""
    digest = hashlib.sha256()
    total = 0
    try:
        with path.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            if (_is_link_or_reparse(opened) or not stat.S_ISREG(opened.st_mode)
                    or (opened.st_dev, opened.st_ino) != (expected.st_dev, expected.st_ino)):
                raise ValueError(f"release archive changed before hashing: {path}")
            for chunk in iter(lambda: handle.read(_RELEASE_CHUNK), b""):
                total += len(chunk)
                if total > _MAX_RELEASE_ARCHIVE_BYTES:
                    raise ValueError(f"release archive exceeds size limit: {path}")
                digest.update(chunk)
            finished = os.fstat(handle.fileno())
    except OSError as exc:
        raise ValueError(f"cannot hash release archive: {path}") from exc
    try:
        current = path.lstat()
    except OSError as exc:
        raise ValueError(f"cannot inspect release archive after hashing: {path}") from exc
    if ((finished.st_dev, finished.st_ino) != (expected.st_dev, expected.st_ino)
            or (current.st_dev, current.st_ino) != (expected.st_dev, expected.st_ino)
            or finished.st_size != expected.st_size
            or current.st_size != expected.st_size
            or finished.st_mtime_ns != expected.st_mtime_ns
            or current.st_mtime_ns != expected.st_mtime_ns):
        raise ValueError(f"release archive changed during hashing: {path}")
    return total, digest.hexdigest()


def _stage_release_archive(archive: Path, target_dir: Path) -> Path:
    """Copy a checked archive to a private stable path before installation."""
    target_dir = _safe_existing_directory(target_dir, "release install directory")
    try:
        expected = archive.lstat()
        if _is_link_or_reparse(expected) or not stat.S_ISREG(expected.st_mode):
            raise ValueError(f"release archive target is unsafe: {archive}")
        if expected.st_size <= 0 or expected.st_size > _MAX_RELEASE_ARCHIVE_BYTES:
            raise ValueError(f"release archive has invalid size: {archive}")
        suffix = ".whl" if archive.name.endswith(".whl") else ".tar.gz"
        staged = target_dir / archive.name
        temporary = None
        with archive.open("rb") as source:
            opened = os.fstat(source.fileno())
            if _is_link_or_reparse(opened) or not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (expected.st_dev, expected.st_ino):
                raise ValueError(f"release archive changed before staging: {archive}")
            with tempfile.NamedTemporaryFile(mode="wb", dir=target_dir, prefix=".staged-", suffix=suffix, delete=False) as destination:
                temporary = Path(destination.name)
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    destination.write(chunk)
                destination.flush()
                os.fsync(destination.fileno())
            finished = os.fstat(source.fileno())
        current = archive.lstat()
        if (finished.st_dev, finished.st_ino) != (expected.st_dev, expected.st_ino) or (current.st_dev, current.st_ino) != (expected.st_dev, expected.st_ino) or current.st_size != expected.st_size or current.st_mtime_ns != expected.st_mtime_ns:
            raise ValueError(f"release archive changed during staging: {archive}")
        # Stat identity cannot detect an attacker that replaces bytes and
        # restores size/mtime. Re-hash the source after copying and compare it
        # with the digest computed from the bytes that were staged.
        source_size, source_digest = _digest_release_file(archive, current)
        staged_size, staged_digest = _digest_release_file(temporary, temporary.lstat())
        if source_size != staged_size or source_digest != staged_digest:
            raise ValueError(f"release archive content changed during staging: {archive}")
        staged_info = temporary.lstat()
        if _is_link_or_reparse(staged_info) or not stat.S_ISREG(staged_info.st_mode) or staged_info.st_size != expected.st_size:
            raise ValueError(f"staged release archive is unsafe: {archive}")
        os.replace(temporary, staged)
        temporary = None
        return staged
    except OSError as exc:
        raise ValueError(f"cannot stage release archive: {archive}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _safe_output_directory(path: Path) -> Path:
    """Create an output directory without following symlinked components."""
    target = Path(path)
    if not target.is_absolute():
        target = Path.cwd() / target
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
    return Path(os.path.normpath(os.fspath(target)))

def verify(root: Path, output: Path) -> None:
    root = _safe_existing_directory(root, "release source checkout")
    output = Path(output)
    if not output.is_absolute():
        output = Path.cwd() / output
    # Keep the original spelling for no-follow component inspection, but use
    # a lexical-normalized copy for containment before creating any directory.
    # Otherwise ``root/../outside`` is falsely rejected while
    # ``other/../root/release`` could create an in-checkout directory before
    # the later resolved containment check fails.
    normalized_output = Path(os.path.normpath(os.fspath(output)))
    if normalized_output == root or normalized_output.is_relative_to(root):
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
    # Build both artifacts from one isolated source snapshot so packaging
    # backends cannot dirty, lock, or execute against the user's checkout.
    with tempfile.TemporaryDirectory(prefix="release-source-", dir=output) as source_dir:
        source_snapshot = Path(source_dir)
        _copy_release_source(root, source_snapshot)
        run([sys.executable, "-m", "pip", "wheel", str(source_snapshot), "--no-deps", "--no-index", "--no-build-isolation", "--wheel-dir", str(wheelhouse)], cwd=source_snapshot)
        build_sdist = "import setuptools.build_meta as b; b.build_sdist(%r)" % str(wheelhouse)
        run([sys.executable, "-c", build_sdist], cwd=source_snapshot)
    archives = _safe_release_archives(wheelhouse)
    for archive in archives:
        # Keep install probes in a per-run temporary directory. This makes the
        # documented command repeatable without deleting arbitrary user files
        # below the caller-selected output directory.
        with tempfile.TemporaryDirectory(prefix="install-", dir=output) as target:
            staged_archive = _stage_release_archive(archive, Path(target))
            run([sys.executable, "-m", "pip", "install", "--no-deps", "--no-index", "--no-build-isolation", "--target", target, str(staged_archive)])
            env = os.environ.copy(); env["PYTHONPATH"] = target
            probe = (
                "from pathlib import Path; "
                "import maintainer_zero; "
                "from importlib.metadata import version as installed_version; "
                "from maintainer_zero.demos import load_demo_suite; "
                "from maintainer_zero.scenario_registry import load_bundled_registry, scenario_ids; "
                "p=Path(maintainer_zero.__file__).resolve(); "
                "assert p.is_relative_to(Path(r'%s').resolve()); "
                "assert installed_version('maintainer-zero') == maintainer_zero.__version__; "
                "registry=load_bundled_registry(); "
                "assert registry.get('schema_version') == 1 and registry.get('scenarios'); "
                "assert scenario_ids(registry) == tuple(sorted(item['id'] for item in registry['scenarios'])); "
                "suite=load_demo_suite(); "
                "assert suite.get('schema_version') == 1 and suite.get('demos'); "
                "print(p)"
            ) % target
            run([sys.executable, "-c", probe], cwd=output, env=env)
            rendered = run([sys.executable, "-m", "maintainer_zero", "demo", "--format", "json", "--fail-on-regression"], cwd=output, env=env)
            payload = json.loads(rendered)
            if payload.get("schema_version") != 1 or len(payload.get("results", [])) != 3:
                raise RuntimeError(f"unexpected demo payload from {archive.name}")
            # Exercise the packaged user's primary path as well: a full local
            # drill must emit both integrity artifacts and verify them without
            # importing the source checkout's package. Build a disposable empty
            # Git repository for this probe instead of handing the live checkout
            # to the installed CLI; this keeps the smoke test independent from
            # concurrent source-tree changes after the release snapshot.
            drill_repository = Path(target) / "smoke-repository"
            drill_repository.mkdir()
            run(["git", "init", "--quiet"], cwd=drill_repository)
            drill_output = Path(target) / "continuity-smoke"
            run([
                sys.executable, "-m", "maintainer_zero", "simulate",
                str(drill_repository), "--scenario", "all", "--days", "7",
                "--output", str(drill_output),
            ], cwd=output, env=env)
            run([
                sys.executable, "-m", "maintainer_zero", "verify-manifest",
                str(drill_output / "artifact-manifest.json"),
            ], cwd=output, env=env)
            run([
                sys.executable, "-m", "maintainer_zero", "verify-credential",
                str(drill_output / "continuity-credential.json"),
            ], cwd=output, env=env)
    print(f"verified {len(archives)} artifacts outside source checkout: {output}")

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).parents[1])
    parser.add_argument("--output", type=Path, default=DEFAULT_VERIFY_OUTPUT)
    args = parser.parse_args(argv)
    try:
        # Preserve caller-supplied paths until ``verify`` applies
        # component-by-component link/reparse checks. Resolving first would
        # follow an unsafe link and bypass the intended boundary check.
        verify(args.root, args.output)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError) as exc:
        print(f"error: release verification failed: {exc.__class__.__name__}")
        return 2
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
