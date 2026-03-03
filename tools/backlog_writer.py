from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List


def _join(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, list):
        return " | ".join(str(i).strip() for i in x if str(i).strip())
    return str(x).strip()


def write_backlog_csv(findings_requirements: Dict[str, Any], out_path: str | Path) -> None:
    """
    UX agent output shape:
      findings_requirements["backlog"] = {"epics": [...], "stories": [...]}
    """
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    backlog = findings_requirements.get("backlog") or {}
    epics = backlog.get("epics") or []
    stories = backlog.get("stories") or []

    rows: List[Dict[str, str]] = []

    for e in epics:
        rows.append(
            {
                "type": "Epic",
                "id": str(e.get("id", "")),
                "title": str(e.get("title", "")),
                "description": str(e.get("description", "")),
                "priority": str(e.get("priority", "")),
                "epic_id": "",
                "acceptance_criteria": "",
                "linked_requirements": "",
                "dependencies": "",
            }
        )

    for s in stories:
        rows.append(
            {
                "type": "Story",
                "id": str(s.get("id", "")),
                "title": str(s.get("title", "")),
                "description": str(s.get("description", "")),
                "priority": str(s.get("priority", "")),
                "epic_id": str(s.get("epic_id", "")),
                "acceptance_criteria": _join(s.get("acceptance_criteria")),
                "linked_requirements": _join(s.get("linked_requirements")),
                "dependencies": _join(s.get("dependencies")),
            }
        )

    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "type",
                "id",
                "title",
                "description",
                "priority",
                "epic_id",
                "acceptance_criteria",
                "linked_requirements",
                "dependencies",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)