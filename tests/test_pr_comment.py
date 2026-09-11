import pytest

from maintainer_zero.pr_comment import PRCommentError, build_comment_draft, publish_comment


def report():
    return {
        "repository": {"name": "demo", "path": "D:/demo"},
        "results": [{"scenario": "ci-outage", "score": 72}],
    }


def test_draft_is_deterministic_and_contains_no_raw_records():
    first = build_comment_draft(report(), {"status": "improved"})
    second = build_comment_draft(report(), {"status": "improved"})
    assert first == second
    assert first["idempotency_key"]
    assert "results" not in first["body"]


def test_publish_requires_explicit_opt_in_and_injected_publisher():
    draft = build_comment_draft(report())
    with pytest.raises(PRCommentError, match="disabled"):
        publish_comment(draft)
    with pytest.raises(PRCommentError, match="publisher"):
        publish_comment(draft, enabled=True)
    calls = []
    result = publish_comment(draft, enabled=True, publisher=lambda **kwargs: calls.append(kwargs) or "comment-1")
    assert result == "comment-1"
    assert calls[0]["idempotency_key"] == draft["idempotency_key"]
