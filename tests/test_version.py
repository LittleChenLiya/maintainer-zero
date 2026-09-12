from pathlib import Path
from importlib.metadata import version as installed_version
import tomllib

import maintainer_zero


def test_package_version_is_consistent_with_project_metadata():
    project = tomllib.loads(
        (Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    )
    assert maintainer_zero.__version__ == project["project"]["version"]
    assert installed_version("maintainer-zero") == project["project"]["version"]
