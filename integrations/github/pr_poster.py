from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ARTIFACT_FILES = [
    "prd.md",
    "roadmap.json",
    "experiment_plan.md",
    "decision_log.md",
    "backlog.csv",
]

# Marker at the start of our comment body so we can find and update it on re-runs
AIPM_COMMENT_MARKER = "## AIPM Run Summary"


def _read_json(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def build_pr_message(run_dir: str | Path) -> str:

    run_path = Path(run_dir).resolve()
    if not run_path.is_dir():
        raise FileNotFoundError(f"Run directory not found: {run_path}")

    rec_path = run_path / "final_recommendation.json"
    if not rec_path.exists():
        raise FileNotFoundError(f"final_recommendation.json not found in {run_path}")

    rec = _read_json(rec_path)
    exec_summary = rec.get("executive_summary") or "N/A"
    gating = rec.get("gating_decision") or "N/A"
    top_risks = rec.get("top_risks") or []
    recommended_direction = rec.get("recommended_direction") or ""
    open_questions = rec.get("open_questions") or []
    decision_rationale = rec.get("decision_rationale") or ""

    schema_status = ""
    schema_path = run_path / "schema_validation.json"
    if schema_path.exists():
        try:
            schema_data = _read_json(schema_path)
            valid = schema_data.get("valid", None)
            if valid is True:
                schema_status = "\n**Schema validation:** valid"
            elif valid is False:
                schema_status = "\n**Schema validation:** invalid"
            else:
                schema_status = "\n**Schema validation:** (partial/skipped)"
        except Exception:
            schema_status = "\n**Schema validation:** (could not read)"

    next_steps: list[str] = []
    if recommended_direction:
        next_steps.append(recommended_direction)
    if decision_rationale and decision_rationale not in next_steps:
        next_steps.append(decision_rationale)
    for q in open_questions[:5]:
        next_steps.append(f"- {q}")

    next_steps_md = "\n".join(next_steps) if next_steps else "See decision log and PRD for details."

    artifacts_lines: list[str] = []
    for name in ARTIFACT_FILES:
        p = run_path / name
        if p.exists():
            artifacts_lines.append(f"- `{name}`")
        else:
            artifacts_lines.append(f"- `{name}` (not generated)")

    run_id = run_path.name
    body = f"""## AIPM Run Summary — `{run_id}`

{exec_summary}
{schema_status}

**{gating}**

{chr(10).join('- ' + r for r in top_risks[:10]) if top_risks else '- None listed.'}

{next_steps_md}

{chr(10).join(artifacts_lines)}

---
*Generated from run directory: `{run_path}`*
"""
    return body.strip()


def _get_issue_comments(
    repo: str,
    issue_number: int,
    token: str,
    api_base: str = "https://api.github.com",
) -> list[dict[str, Any]]:
    """GET issue/PR comments. Used to find existing AIPM comment for update."""
    owner, repo_name = repo.split("/", 1) if "/" in repo else (repo, "")
    if not repo_name:
        raise ValueError("repo must be in form owner/repo")
    url = f"{api_base.rstrip('/')}/repos/{owner}/{repo_name}/issues/{issue_number}/comments"
    req = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
        },
        method="GET",
    )
    with urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _update_issue_comment(
    comment_url: str,
    body: str,
    token: str,
) -> dict[str, Any]:
    """PATCH an issue comment by URL (from comment['url'])."""
    req = Request(
        comment_url,
        data=json.dumps({"body": body}).encode("utf-8"),
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="PATCH",
    )
    with urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def post_pr_comment(
    repo: str,
    pr_number: int,
    body: str,
    token: str,
    update_if_exists: bool = False,
    api_base: str = "https://api.github.com",
) -> dict[str, Any]:
    """
    Post an issue/PR comment. If update_if_exists=True, find an existing comment
    that starts with AIPM_COMMENT_MARKER and PATCH it instead of posting a new one.
    """
    owner, repo_name = repo.split("/", 1) if "/" in repo else (repo, "")
    if not repo_name:
        raise ValueError("repo must be in form owner/repo")

    if update_if_exists:
        try:
            comments = _get_issue_comments(repo, pr_number, token, api_base)
            for c in comments:
                if (c.get("body") or "").strip().startswith(AIPM_COMMENT_MARKER):
                    return _update_issue_comment(c["url"], body, token)
        except (HTTPError, URLError, RuntimeError):
            pass

    url = f"{api_base.rstrip('/')}/repos/{owner}/{repo_name}/issues/{pr_number}/comments"
    data = json.dumps({"body": body}).encode("utf-8")
    req = Request(
        url,
        data=data,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        body_read = e.read().decode("utf-8") if e.fp else ""
        raise RuntimeError(f"GitHub API error {e.code}: {body_read}") from e
    except URLError as e:
        raise RuntimeError(f"Request failed: {e.reason}") from e


def post_pr_review_comment(
    repo: str,
    pr_number: int,
    body: str,
    token: str,
    commit_id: str | None = None,
    event: str = "COMMENT",
    api_base: str = "https://api.github.com",
) -> dict[str, Any]:
    """
    Post a PR review with event=COMMENT (no approval/request changes).
    Optional: pass commit_id for the head of the PR to attach review to a commit.
    """
    owner, repo_name = repo.split("/", 1) if "/" in repo else (repo, "")
    if not repo_name:
        raise ValueError("repo must be in form owner/repo")

    url = f"{api_base.rstrip('/')}/repos/{owner}/{repo_name}/pulls/{pr_number}/reviews"
    payload: dict[str, Any] = {"body": body, "event": event}
    if commit_id:
        payload["commit_id"] = commit_id
    data = json.dumps(payload).encode("utf-8")
    req = Request(
        url,
        data=data,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        body_read = e.read().decode("utf-8") if e.fp else ""
        raise RuntimeError(f"GitHub API error {e.code}: {body_read}") from e
    except URLError as e:
        raise RuntimeError(f"Request failed: {e.reason}") from e
