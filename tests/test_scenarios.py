from maintainer_zero.models import RepoSnapshot
from maintainer_zero.scenarios import ci_outage, dependency_yanked, maintainer_zero

def repo(**kwargs):
    defaults = dict(path=".", name="demo", commits=100, contributors={"A": 80, "B": 20}, dependencies=["requests", "numpy"], workflows=["ci.yml"], codeowners={"*": ["@a"]}, release_files=[".github/workflows/release.yml"])
    defaults.update(kwargs)
    return RepoSnapshot(**defaults)

def test_maintainer_drill_flags_single_point():
    result = maintainer_zero(repo())
    assert result.scenario == "maintainer-zero"
    assert 0 <= result.score <= 100
    assert any(f.title == "核心维护单点" for f in result.findings)
    assert result.metrics["departed_maintainer"] == "A"

def test_dependency_drill_is_deterministic():
    first = dependency_yanked(repo())
    second = dependency_yanked(repo())
    assert first.to_dict() == second.to_dict()
    assert first.metrics["dependency_count"] == 2

def test_ci_drill_detects_release_path():
    result = ci_outage(repo())
    assert result.metrics["release_path_detected"] is True
    assert result.findings[0].severity == "high"
