"""
Ingest Jira issues (via JQL or project) into a local Product Bundle.
Creates bundles/jira_<project>_<timestamp>/ with bundle_manifest.json, tickets.json,
and optional customer_notes.md from comments.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List

from tools.io_utils import write_json, write_text

# Allowed ticket types in our schema
TICKET_TYPES = {"Bug", "Feature", "Story", "Task", "Epic", "UX", "Performance"}
PRIORITIES = {"Critical", "High", "Medium", "Low"}


def _jira_issue_to_ticket(issue: dict, base_url: str) -> dict[str, Any]:
    """Map one Jira issue (REST API shape) to our ticket schema."""
    key = issue.get("key") or issue.get("id", "")
    fields = issue.get("fields") or {}
    summary = (fields.get("summary") or "").strip()
    desc = fields.get("description")
    if isinstance(desc, dict):
        # Jira can return description as ADF (Atlassian Document Format)
        desc = _adf_to_plain(desc) if isinstance(desc, dict) else str(desc or "")
    else:
        desc = str(desc or "").strip()
    priority_obj = fields.get("priority")
    priority = priority_obj.get("name", "Medium") if isinstance(priority_obj, dict) else "Medium"
    if priority not in PRIORITIES:
        priority = "Medium"
    status_obj = fields.get("status")
    status = status_obj.get("name", "Open") if isinstance(status_obj, dict) else "Open"
    labels = fields.get("labels") or []
    created = fields.get("created") or ""
    updated = fields.get("updated") or ""
    issuetype_obj = fields.get("issuetype")
    itype = issuetype_obj.get("name", "Task") if isinstance(issuetype_obj, dict) else "Task"
    if itype not in TICKET_TYPES:
        itype = "Task"
    link = f"{base_url.rstrip('/')}/browse/{key}" if base_url and key else ""

    return {
        "id": key,
        "key": key,
        "title": summary or key,
        "description": desc,
        "type": itype,
        "priority": priority,
        "status": status,
        "source": "Jira",
        "created_at": created,
        "updated_at": updated,
        "labels": labels if isinstance(labels, list) else [],
        "url": link,
    }


def _adf_to_plain(node: dict) -> str:
    """Best-effort extract plain text from Atlassian Document Format."""
    if not isinstance(node, dict):
        return str(node)
    text = node.get("text") or ""
    content = node.get("content") or []
    for c in content:
        if isinstance(c, dict):
            text += _adf_to_plain(c)
    return text


def _comments_summary(issues: List[dict], max_comments: int = 20) -> str:
    """Build a short customer_notes-style summary from issue comments (top N)."""
    lines: List[str] = []
    for issue in issues[:50]:
        key = issue.get("key", "")
        fields = issue.get("fields") or {}
        comment_obj = fields.get("comment")
        if not isinstance(comment_obj, dict):
            continue
        comments = comment_obj.get("comments") or []
        for c in comments[:3]:
            if len(lines) >= max_comments:
                return "\n\n".join(lines)
            body = c.get("body")
            if isinstance(body, dict):
                body = _adf_to_plain(body)
            author = (c.get("author") or {}).get("displayName", "Unknown")
            created = c.get("created", "")[:10]
            snippet = (str(body or "").strip()[:200]).replace("\n", " ")
            if snippet:
                lines.append(f"[{key}] {created} {author}: {snippet}")
    return "\n\n".join(lines) if lines else ""


def ingest_jira_to_bundle(
    jql: str,
    base_url: str | None = None,
    email: str | None = None,
    api_token: str | None = None,
    bundles_dir: Path | str | None = None,
    project_key: str | None = None,
    max_issues: int = 500,
    include_comment_notes: bool = True,
    max_comment_snippets: int = 15,
    _issues_override: List[dict] | None = None,
) -> Path:
    """
    Fetch issues from Jira (by JQL) and write a local bundle under bundles/jira_<project>_<timestamp>/.

    If _issues_override is provided, Jira is not called (for tests). Otherwise base_url, email, api_token
    can come from env (JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN).

    Returns the path to the created bundle directory.
    """
    if bundles_dir is None:
        bundles_dir = Path(__file__).resolve().parent.parent.parent / "bundles"
    bundles_dir = Path(bundles_dir)
    bundles_dir.mkdir(parents=True, exist_ok=True)

    # Derive project from JQL if not given (e.g. "project = PROJ" -> PROJ)
    if not project_key and jql:
        m = re.search(r"project\s*=\s*([A-Za-z0-9_]+)", jql, re.IGNORECASE)
        if m:
            project_key = m.group(1)
    if not project_key:
        project_key = "jira"
    safe_project = re.sub(r"[^\w-]", "_", project_key)[:32]
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    bundle_id = f"jira_{safe_project}_{ts}"
    bundle_path = bundles_dir / bundle_id
    bundle_path.mkdir(parents=True, exist_ok=True)

    if _issues_override is not None:
        issues = _issues_override
        base_url = base_url or "https://example.atlassian.net"
    else:
        from integrations.jira.client import JiraClient

        client = JiraClient(base_url=base_url, email=email, api_token=api_token)
        base_url = client.base_url
        issues = []
        start_at = 0
        page_size = min(50, max_issues)
        while start_at < max_issues:
            page = client.search_issues(jql, max_results=page_size, start_at=start_at)
            if not page:
                break
            issues.extend(page)
            start_at += len(page)
            if len(page) < page_size:
                break

    tickets = [_jira_issue_to_ticket(iss, base_url or "") for iss in issues]
    if not tickets:
        # Schema requires minItems: 1; add a placeholder so bundle is valid
        tickets = [
            {
                "id": "NO-ISSUES",
                "key": "NO-ISSUES",
                "title": "No issues matched JQL",
                "description": f"JQL: {jql}",
                "type": "Task",
                "priority": "Medium",
                "status": "Open",
                "source": "Jira",
                "created_at": datetime.now(timezone.utc).isoformat()[:19] + "Z",
                "updated_at": "",
                "labels": [],
                "url": "",
            }
        ]

    write_json(bundle_path / "tickets.json", {"tickets": tickets})

    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    manifest = {
        "bundle_id": bundle_id,
        "created_at": created_at,
        "source": "jira",
        "files": {
            "request": "product_request.md",
            "tickets": "tickets.json",
            "customer_notes": "customer_notes.md",
            "metrics_snapshot": "metrics_snapshot.json",
            "competitors": "competitors.md",
        },
    }
    write_json(bundle_path / "bundle_manifest.json", manifest)

    write_text(bundle_path / "product_request.md", f"# Ingested from Jira\n\nJQL: `{jql}`\n\nNo product request file; add one for full pipeline.\n")
    # Minimal valid metrics_snapshot for schema validation (time_window pattern required)
    write_json(
        bundle_path / "metrics_snapshot.json",
        {"time_window": "2020-01-01_to_2020-01-31", "note": "Placeholder; add real metrics for metrics agent."},
    )
    write_text(bundle_path / "competitors.md", "")

    if include_comment_notes and issues and not _issues_override:
        notes = _comments_summary(issues, max_comments=max_comment_snippets)
        if notes:
            write_text(bundle_path / "customer_notes.md", f"# Customer notes (from Jira comments)\n\n{notes}\n")
        else:
            write_text(bundle_path / "customer_notes.md", "")
    else:
        if _issues_override and include_comment_notes:
            notes = _comments_summary(issues, max_comments=max_comment_snippets)
            write_text(bundle_path / "customer_notes.md", notes or "# No comments\n")
        else:
            write_text(bundle_path / "customer_notes.md", "")

    return bundle_path
