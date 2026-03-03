from __future__ import annotations

from datetime import datetime
from pathlib import Path

from tools.io_utils import read_json, write_json, write_text
from tools.logging_utils import get_logger

# Project root = parent of orchestration/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = PROJECT_ROOT / "runs"


def _run_dir_name(bundle_name: str) -> str:
    """e.g. 2026-03-02_1530_sample_01"""
    now = datetime.now()
    return f"{now:%Y-%m-%d_%H%M}_{bundle_name}"


def _create_placeholders(out_dir: Path) -> None:
    """Create empty/placeholder artifact files in out_dir."""
    placeholders = [
        "prd.md",
        "experiment_plan.md",
        "decision_log.md",
    ]
    for name in placeholders:
        p = out_dir / name
        if not p.exists():
            write_text(p, "")

    # JSON placeholders
    for name in ["roadmap.json"]:
        p = out_dir / name
        if not p.exists():
            write_json(p, {})

    # CSV placeholder (header-only, so Excel opens it nicely)
    backlog_path = out_dir / "backlog.csv"
    if not backlog_path.exists():
        write_text(
            backlog_path,
            "type,id,title,description,priority,epic_id,acceptance_criteria,linked_requirements,dependencies\n",
        )


def run_pipeline(bundle_path: str, out_dir: str | None = None) -> str:
    """
    Run the pipeline for the given bundle:
      - Intake Agent -> context_packet.json (+ evidence_index.json)
      - Metrics Agent -> findings_metrics.json
      - UX/Requirements Agent -> findings_requirements.json
      - Backlog writer -> backlog.csv
      - Placeholders for other artifacts

    Creates runs/YYYY-MM-DD_HHMM_<bundle_name>/ and returns its path.
    """
    bundle_path = Path(bundle_path).resolve()
    if not bundle_path.is_dir():
        raise FileNotFoundError(f"Bundle not found: {bundle_path}")

    bundle_name = bundle_path.name
    run_name = _run_dir_name(bundle_name)
    target_dir = RUNS_DIR / run_name if out_dir is None else Path(out_dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    log = get_logger("pipeline")

    # 1) Intake Agent (Intern 3): context_packet.json + evidence_index.json
    try:
        from agents.intake_context_agent import run as intake_run

        intake_run(bundle_path, target_dir)
    except Exception as e:
        # If intake fails, still write a minimal context packet so downstream agents don't crash
        write_json(
            target_dir / "context_packet.json",
            {
                "bundle_id": bundle_name,
                "request_summary": "",
                "tickets": [],
                "risk_hotspots": {},
                "bundle_level_risks": [],
                "missing_info": [],
                "ignored_items": [],
                "duplicates": [],
                "warnings": [f"Intake agent failed: {e}"],
            },
        )
        log.warning("Intake agent failed: %s; wrote placeholder context_packet.json", e)

    # Load context once
    context_path = target_dir / "context_packet.json"
    try:
        context_packet = read_json(context_path) if context_path.exists() else {"bundle_id": bundle_name}
    except Exception as e:
        context_packet = {"bundle_id": bundle_name}
        log.warning("Failed to read context_packet.json: %s", e)

    # 2) Metrics & Analytics Agent (Agent D): findings_metrics.json (always write something)
    try:
        from agents.metrics_analytics_agent import run as metrics_run

        findings = metrics_run(context_packet)
        write_json(target_dir / "findings_metrics.json", findings)
    except Exception as e:
        log.warning("Metrics analytics agent failed: %s", e)
        write_json(
            target_dir / "findings_metrics.json",
            {
                "bundle_id": bundle_name,
                "feature_area": "",
                "goals": [],
                "north_star_metric": None,
                "input_metrics": [],
                "guardrails": [],
                "event_taxonomy": [],
                "issues": ["metrics_agent_failed"],
                "recommendations": [],
                "warnings": [str(e)],
            },
        )

    # 3) UX & Requirements Agent (Agent E): findings_requirements.json (always write something)
    try:
        from agents.ux_requirements_agent import run as req_run

        req_findings = req_run(context_packet)
        write_json(target_dir / "findings_requirements.json", req_findings)

        # 4) Backlog CSV generator from req_findings["backlog"]
        from tools.backlog_writer import write_backlog_csv

        write_backlog_csv(req_findings, target_dir / "backlog.csv")
    except Exception as e:
        log.warning("UX requirements agent failed: %s", e)
        write_json(
            target_dir / "findings_requirements.json",
            {
                "bundle_id": bundle_name,
                "summary": "",
                "journeys": [],
                "requirements": [],
                "edge_cases": [],
                "backlog": {"epics": [], "stories": []},
                "warnings": [str(e)],
            },
        )
        # Ensure backlog exists even if generation failed
        _create_placeholders(target_dir)

    # 5) Placeholders for other artifacts
    _create_placeholders(target_dir)

    return str(target_dir)