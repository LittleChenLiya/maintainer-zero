from pathlib import Path
import re

from maintainer_zero.demos import load_demo_suite, run_demo_suite


ROOT = Path(__file__).parents[1]


def test_public_support_and_issue_routing_are_present():
    support = (ROOT / "SUPPORT.md").read_text(encoding="utf-8")
    issue_config = (ROOT / ".github" / "ISSUE_TEMPLATE" / "config.yml").read_text(encoding="utf-8")

    assert "GitHub Discussions" in support
    assert "SECURITY.md" in support
    assert "blank_issues_enabled: false" in issue_config
    assert "https://github.com/LittleChenLiya/maintainer-zero/discussions" in issue_config
    assert "https://github.com/LittleChenLiya/maintainer-zero/blob/main/SECURITY.md" in issue_config
    conduct = (ROOT / "CODE_OF_CONDUCT.md").read_text(encoding="utf-8")
    assert "## Expected behavior" in conduct
    assert "## Reporting" in conduct
    assert "SECURITY.md" in conduct


def test_public_quick_start_uses_portable_source_commands_and_real_demo_output():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    quick_start = readme.split("## Quick start\n", 1)[1].split("\n## ", 1)[0]
    assert "git clone https://github.com/LittleChenLiya/maintainer-zero.git" in quick_start
    assert "python -m maintainer_zero demo --fail-on-regression" in quick_start
    assert "python -m maintainer_zero simulate . --scenario all --output .continuity" in quick_start
    assert "D:\\maintainer-zero" not in quick_start
    assert "synthetic" in quick_start
    for result in run_demo_suite(load_demo_suite()):
        expected = (
            f"{result['id']} ({result['scenario']}): "
            f"{result['before_score']} -> {result['after_score']} "
            f"({result['score_delta']:+d}, improved)"
        )
        assert expected in quick_start


def test_short_launch_post_fits_and_preserves_alpha_limits():
    launch_kit = (ROOT / "docs" / "LAUNCH_KIT.md").read_text(encoding="utf-8")
    section = launch_kit.split("## X / Twitter 短帖\n", 1)[1].split("\n## ", 1)[0]
    post = section.split("~~~text\n", 1)[1].split("\n~~~", 1)[0]
    assert post.isascii()
    # X counts an HTTPS URL as 23 characters; this draft otherwise uses ASCII.
    assert len(re.sub(r"https://\S+", "x" * 23, post)) <= 280
    for boundary in ("alpha", "offline-by-default", "Heuristic",
                     "No automatic GitHub writes", "no security certification",
                     "real recovery proof"):
        assert boundary in post
