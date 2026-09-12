from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

@dataclass
class RepoSnapshot:
    path: str
    name: str
    commits: int = 0
    contributors: dict[str, int] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)
    workflows: list[str] = field(default_factory=list)
    codeowners: dict[str, list[str]] = field(default_factory=dict)
    release_files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass
class Finding:
    severity: str
    title: str
    detail: str
    action: str
    finding_id: str = ""

@dataclass
class Evidence:
    """One bounded observation supporting a drill conclusion."""

    source: str
    field: str
    observed: Any
    note: str = ""

@dataclass
class DrillResult:
    scenario: str
    score: int
    confidence: str
    assumptions: list[str]
    metrics: dict[str, Any]
    findings: list[Finding]
    timeline: list[dict[str, Any]]
    evidence: list[Evidence] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data
