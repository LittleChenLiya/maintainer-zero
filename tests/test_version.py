from pathlib import Path
from importlib.metadata import version as installed_version
try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 CI uses the backport.
    import tomli as tomllib

import maintainer_zero


def test_package_version_is_consistent_with_project_metadata():
    project = tomllib.loads(
        (Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    )
    assert maintainer_zero.__version__ == project["project"]["version"]
    assert installed_version("maintainer-zero") == project["project"]["version"]


def test_project_metadata_points_to_the_public_repository():
    project = tomllib.loads(
        (Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]
    assert project["requires-python"] == ">=3.10"
    assert "Development Status :: 3 - Alpha" in project["classifiers"]
    assert project["urls"]["Repository"] == "https://github.com/LittleChenLiya/maintainer-zero"
    assert project["urls"]["Issues"].endswith("/issues")
    assert project["urls"]["Discussions"].endswith("/discussions")


def test_citation_metadata_matches_public_release_identity():
    citation = (Path(__file__).parents[1] / "CITATION.cff").read_text(encoding="utf-8")
    fields = {}
    for line in citation.splitlines():
        if ": " in line and not line.startswith(" "):
            key, value = line.split(": ", 1)
            fields[key] = value.strip().strip('"')
    project = tomllib.loads(
        (Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]
    assert fields["cff-version"] == "1.2.0"
    assert fields["version"] == project["version"]
    assert fields["repository-code"] == project["urls"]["Repository"]
    assert fields["url"] == project["urls"]["Homepage"]
    assert fields["license"] == "MIT"
