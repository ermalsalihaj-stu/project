from __future__ import annotations
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from integrations.github.pr_poster import build_pr_message, post_pr_comment


def test_build_pr_message_from_run_dir():
    run_dir = Path(__file__).resolve().parent.parent / "runs" / "2026-03-05_1638_sample_01"
    if not run_dir.exists():
        pytest.skip(f"Sample run dir not found: {run_dir}")

    body = build_pr_message(run_dir)
    assert "Executive summary" in body
    assert "Gating decision" in body
    assert "Validate first" in body or "Proceed" in body or "Do not pursue" in body
    assert "Top risks" in body
    assert "Suggested next steps" in body
    assert "Generated artifacts" in body
    assert "prd.md" in body
    assert "decision_log.md" in body
    assert "backlog.csv" in body
    assert "Schema validation" in body


def test_build_pr_message_raises_if_no_final_recommendation(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match="final_recommendation.json"):
        build_pr_message(tmp_path)


def test_post_pr_comment_makes_post_to_correct_endpoint():
    expected_url = "https://api.github.com/repos/owner/repo/issues/42/comments"
    captured = {}

    def capture_request(req):
        captured["request"] = req
        return MagicMock(
            read=lambda: json.dumps({"id": 1, "html_url": "https://github.com/owner/repo/issues/42#issuecomment-1"}).encode(),
            __enter__=lambda self: self,
            __exit__=lambda *a: None,
        )

    with patch("integrations.github.pr_poster.urlopen", side_effect=capture_request):
        result = post_pr_comment("owner/repo", 42, "**Summary**\nDone.", "fake-token")

    assert result.get("html_url") == "https://github.com/owner/repo/issues/42#issuecomment-1"
    req = captured["request"]
    assert req.get_method() == "POST"
    assert req.full_url == expected_url
    assert "Authorization" in req.headers
    assert req.headers["Authorization"] == "Bearer fake-token"
    payload = json.loads(req.data.decode("utf-8"))
    assert payload["body"] == "**Summary**\nDone."
