"""Compose the bounded read-only GitHub client for an explicit repository slug."""

from __future__ import annotations

import re
from typing import Any, Callable

from .github_client import (
    DEFAULT_MAX_PAGES,
    DEFAULT_MAX_RESPONSE_BYTES,
    DEFAULT_PAGE_SIZE,
    DEFAULT_TIMEOUT_SECONDS,
    ReadOnlyGitHubClient,
    TransportResponse,
)

_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")


class GitHubRepositoryError(ValueError):
    """Raised when an owner/repository slug is outside the safe path envelope."""


def validate_repository_slug(repository: str) -> str:
    if not isinstance(repository, str) or not _SLUG_RE.fullmatch(repository):
        raise GitHubRepositoryError("repository must use OWNER/REPOSITORY format")
    owner, name = repository.split("/", 1)
    if owner in {".", ".."} or name in {".", ".."}:
        raise GitHubRepositoryError("repository contains an invalid path component")
    return repository


def repository_paths(repository: str) -> dict[str, str]:
    repository = validate_repository_slug(repository)
    prefix = f"/repos/{repository}"
    return {
        "issues": f"{prefix}/issues",
        "pull_requests": f"{prefix}/pulls",
        "releases": f"{prefix}/releases",
    }


def collect_repository_metadata(
    repository: str,
    fetch: Callable[[str, dict[str, str], float], TransportResponse],
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    max_pages: int = DEFAULT_MAX_PAGES,
    page_size: int = DEFAULT_PAGE_SIZE,
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
) -> dict[str, Any]:
    """Collect only bounded read-only metadata through a caller-owned transport."""
    return ReadOnlyGitHubClient(
        fetch,
        timeout_seconds=timeout_seconds,
        max_pages=max_pages,
        page_size=page_size,
        max_response_bytes=max_response_bytes,
    ).collect(repository_paths(repository))


__all__ = [
    "GitHubRepositoryError",
    "collect_repository_metadata",
    "repository_paths",
    "validate_repository_slug",
]
