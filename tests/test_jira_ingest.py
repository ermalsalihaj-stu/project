"""
Tests for Jira ingest: ingest_jira_to_bundle creates a valid bundle with tickets.json.
Uses mock (no real Jira): _issues_override or monkeypatch requests.
"""
from pathlib import Path

import pytest


# Fake Jira search response (REST API shape)
FAKE_JIRA_ISSUES = [
    {
        "key": "PROJ-1",
        "id": "10001",
        "fields": {
            "summary": "Fix login button",
            "description": "The login button does not respond on Safari.",
            "priority": {"name": "High"},
            "status": {"name": "Open"},
            "labels": ["bug", "frontend"],
            "created": "2026-03-01T10:00:00.000+0000",
            "updated": "2026-03-02T11:00:00.000+0000",
            "issuetype": {"name": "Bug"},
        },
    },
    {
        "key": "PROJ-2",
        "id": "10002",
        "fields": {
            "summary": "Add checkout step",
            "description": "Add a new step for payment method selection.",
            "priority": {"name": "Medium"},
            "status": {"name": "In Progress"},
            "labels": [],
            "created": "2026-03-02T09:00:00.000+0000",
            "updated": "2026-03-03T14:00:00.000+0000",
            "issuetype": {"name": "Story"},
        },
    },
]


def test_ingest_jira_to_bundle_creates_tickets_json(tmp_path):
    """Ingest with _issues_override creates bundle dir and tickets.json (no real Jira call)."""
    from integrations.jira.ingest import ingest_jira_to_bundle

    bundles_dir = tmp_path / "bundles"
    bundle_path = ingest_jira_to_bundle(
        jql="project = PROJ",
        bundles_dir=bundles_dir,
        _issues_override=FAKE_JIRA_ISSUES,
        include_comment_notes=False,
    )

    assert bundle_path.exists()
    assert bundle_path.is_dir()
    assert (bundle_path / "tickets.json").exists()
    assert (bundle_path / "bundle_manifest.json").exists()
    assert (bundle_path / "product_request.md").exists()
    assert (bundle_path / "customer_notes.md").exists()
    assert (bundle_path / "metrics_snapshot.json").exists()
    assert (bundle_path / "competitors.md").exists()

    import json
    tickets_data = json.loads((bundle_path / "tickets.json").read_text(encoding="utf-8"))
    assert "tickets" in tickets_data
    tickets = tickets_data["tickets"]
    assert len(tickets) == 2
    assert tickets[0]["id"] == "PROJ-1"
    assert tickets[0]["title"] == "Fix login button"
    assert tickets[0]["type"] == "Bug"
    assert tickets[0]["priority"] == "High"
    assert tickets[1]["id"] == "PROJ-2"
    assert tickets[1]["title"] == "Add checkout step"
    assert tickets[1]["type"] == "Story"

    manifest = json.loads((bundle_path / "bundle_manifest.json").read_text(encoding="utf-8"))
    assert manifest["source"] == "jira"
    assert manifest["bundle_id"].startswith("jira_")
    assert manifest["files"]["tickets"] == "tickets.json"


def test_ingest_jira_to_bundle_validates_with_validate_bundle(tmp_path):
    """Bundle created by ingest passes validate_bundle (schema check)."""
    from tools.validate_bundle import validate_bundle

    from integrations.jira.ingest import ingest_jira_to_bundle

    bundle_path = ingest_jira_to_bundle(
        jql="project = PROJ",
        bundles_dir=tmp_path / "bundles",
        _issues_override=FAKE_JIRA_ISSUES,
        include_comment_notes=False,
    )

    errors, warnings = validate_bundle(bundle_path)
    assert not errors, f"Validation errors: {errors}"
    # Warnings (e.g. docs_dir) are acceptable


def test_ingest_jira_empty_jql_creates_placeholder_ticket(tmp_path):
    """When no issues returned, bundle still has one placeholder ticket so schema is valid."""
    from integrations.jira.ingest import ingest_jira_to_bundle

    bundle_path = ingest_jira_to_bundle(
        jql="project = EMPTY",
        bundles_dir=tmp_path / "bundles",
        _issues_override=[],  # no issues
        include_comment_notes=False,
    )

    import json
    tickets_data = json.loads((bundle_path / "tickets.json").read_text(encoding="utf-8"))
    assert len(tickets_data["tickets"]) == 1
    assert tickets_data["tickets"][0]["id"] == "NO-ISSUES"
    assert "No issues matched" in tickets_data["tickets"][0]["title"]


def test_ingest_then_run_pipeline(tmp_path):
    """After ingest, run pipeline on the created bundle (DoD: run --bundle <that_bundle> works)."""
    from orchestration.pipeline import run_pipeline

    from integrations.jira.ingest import ingest_jira_to_bundle

    bundles_dir = tmp_path / "bundles"
    bundle_path = ingest_jira_to_bundle(
        jql="project = PROJ",
        bundles_dir=bundles_dir,
        _issues_override=FAKE_JIRA_ISSUES,
        include_comment_notes=False,
    )
    out_dir = tmp_path / "out"
    run_pipeline(str(bundle_path), out_dir=str(out_dir))

    assert (out_dir / "context_packet.json").exists()
    assert (out_dir / "findings_metrics.json").exists()
    assert (out_dir / "tickets.json").exists() is False  # tickets are in bundle, not run dir
    import json
    cp = json.loads((out_dir / "context_packet.json").read_text(encoding="utf-8"))
    assert "tickets" in cp
    assert len(cp["tickets"]) >= 2


def test_jira_client_search_issues_mock(monkeypatch):
    """JiraClient.search_issues returns list of issues; mock requests.get."""
    import json
    from unittest.mock import MagicMock

    from integrations.jira.client import JiraClient

    def fake_get(*args, **kwargs):
        r = MagicMock()
        r.raise_for_status = MagicMock()
        r.json.return_value = {"issues": FAKE_JIRA_ISSUES, "total": 2, "startAt": 0, "maxResults": 50}
        return r

    monkeypatch.setattr("integrations.jira.client.requests.Session.get", fake_get)

    client = JiraClient(
        base_url="https://test.atlassian.net",
        email="test@example.com",
        api_token="secret",
    )
    issues = client.search_issues("project = PROJ", max_results=10)
    assert len(issues) == 2
    assert issues[0]["key"] == "PROJ-1"
    assert issues[0]["fields"]["summary"] == "Fix login button"
