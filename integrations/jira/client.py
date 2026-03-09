"""
Jira REST API client for searching issues.
Uses env: JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN (or pass explicitly).
"""
from __future__ import annotations

import os
from typing import Any, List

import requests


def _default_base_url() -> str:
    url = os.environ.get("JIRA_BASE_URL", "").rstrip("/")
    if not url:
        raise ValueError("JIRA_BASE_URL is not set (env or pass base_url)")
    return url


def _default_auth() -> tuple[str, str]:
    email = os.environ.get("JIRA_EMAIL", "")
    token = os.environ.get("JIRA_API_TOKEN", "")
    if not email or not token:
        raise ValueError("JIRA_EMAIL and JIRA_API_TOKEN must be set (env or pass)")
    return (email, token)


class JiraClient:
    """Minimal Jira REST client for search."""

    def __init__(
        self,
        base_url: str | None = None,
        email: str | None = None,
        api_token: str | None = None,
    ):
        self.base_url = (base_url or _default_base_url()).rstrip("/")
        self.auth = (email or _default_auth()[0], api_token or _default_auth()[1])
        self.session = requests.Session()
        self.session.auth = self.auth
        self.session.headers["Accept"] = "application/json"
        self.session.headers["Content-Type"] = "application/json"

    def search_issues(
        self,
        jql: str,
        max_results: int = 50,
        start_at: int = 0,
        fields: list[str] | None = None,
    ) -> List[dict[str, Any]]:
        """
        Run JQL search and return list of issue dicts (raw API shape).
        Each issue has 'key', 'id', 'fields' (summary, description, priority, status, labels, created, updated, issuetype, etc.).
        """
        url = f"{self.base_url}/rest/api/3/search"
        req_fields = fields or [
            "summary",
            "description",
            "priority",
            "status",
            "labels",
            "created",
            "updated",
            "issuetype",
            "comment",
        ]
        params = {
            "jql": jql,
            "maxResults": max_results,
            "startAt": start_at,
            "fields": ",".join(req_fields),
        }
        resp = self.session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data.get("issues") or []
