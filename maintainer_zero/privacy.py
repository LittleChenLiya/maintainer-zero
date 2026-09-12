"""Shared privacy contracts for report and recovery artifact boundaries."""

from __future__ import annotations

import re

from .models import RepoSnapshot

_PRIVACY_FIELDS = frozenset({"anonymize_people", "anonymize_repository", "upload_repository_content"})
_CONTRIBUTOR_ID = re.compile(r"^contributor-[1-9][0-9]*$")
_OWNER_ID = re.compile(r"^@owner-[1-9][0-9]*$")
_REPOSITORY_ID = re.compile(r"^repository-[0-9a-f]{12}$")


def validate_privacy_summary(privacy_summary: dict | None) -> dict | None:
    """Canonicalize and fail closed on the supported privacy options."""
    if privacy_summary is None:
        return None
    if not isinstance(privacy_summary, dict):
        raise ValueError("privacy_summary must be an object")
    unsupported = set(privacy_summary) - _PRIVACY_FIELDS
    if unsupported:
        raise ValueError(
            f"privacy_summary contains unsupported fields: {', '.join(sorted(map(str, unsupported)))}"
        )
    for key in _PRIVACY_FIELDS:
        if key in privacy_summary and not isinstance(privacy_summary[key], bool):
            raise ValueError(f"privacy_summary.{key} must be boolean")
    if privacy_summary.get("upload_repository_content") is True:
        raise ValueError("repository uploads are not supported by report output")
    return {
        "anonymize_people": privacy_summary.get("anonymize_people", False) is True,
        "anonymize_repository": privacy_summary.get("anonymize_repository", False) is True,
        "upload_repository_content": False,
    }


def validate_snapshot_projection(repo: RepoSnapshot, privacy_summary: dict | None) -> dict | None:
    """Ensure a declared anonymization policy matches the snapshot being exported."""
    summary = validate_privacy_summary(privacy_summary)
    if summary is None:
        return None
    if summary["anonymize_people"]:
        if any(not _CONTRIBUTOR_ID.fullmatch(name) for name in repo.contributors):
            raise ValueError("privacy summary requires anonymized contributor identities")
        owners = [owner for entries in repo.codeowners.values() for owner in entries]
        if any(not _OWNER_ID.fullmatch(owner) for owner in owners):
            raise ValueError("privacy summary requires anonymized CODEOWNERS identities")
    if summary["anonymize_repository"]:
        if repo.path != "<local-repository>" or not _REPOSITORY_ID.fullmatch(repo.name):
            raise ValueError("privacy summary requires an anonymized repository identity")
    return summary
