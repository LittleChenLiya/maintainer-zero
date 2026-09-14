from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_public_support_and_issue_routing_are_present():
    support = (ROOT / "SUPPORT.md").read_text(encoding="utf-8")
    issue_config = (ROOT / ".github" / "ISSUE_TEMPLATE" / "config.yml").read_text(encoding="utf-8")

    assert "GitHub Discussions" in support
    assert "SECURITY.md" in support
    assert "blank_issues_enabled: false" in issue_config
    assert "https://github.com/LittleChenLiya/maintainer-zero/discussions" in issue_config
    assert "https://github.com/LittleChenLiya/maintainer-zero/blob/main/SECURITY.md" in issue_config
