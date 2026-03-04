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


def run_pipeline(bundle_path: str, out_dir: str | None = None, strict: bool = False, fail_on_warnings: bool = False) -> str:
    """
    Run the pipeline for the given bundle:
      - Intake Agent -> context_packet.json (+ evidence_index.json)
      - Metrics Agent -> findings_metrics.json
      - UX/Requirements Agent -> findings_requirements.json
      - Backlog writer -> backlog.csv
      - Tech Feasibility & Delivery Agent -> findings_feasibility.json
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

    # 2b) Customer Insights Agent (Agent B): findings_customer.json
    try:
        from agents.customer_insights_agent import run as customer_insights_run

        findings_customer = customer_insights_run(context_packet)
        write_json(target_dir / "findings_customer.json", findings_customer)
    except Exception as e:
        log.warning("Customer insights agent failed: %s", e)
        write_json(
            target_dir / "findings_customer.json",
            {
                "bundle_id": bundle_name,
                "segments": [
                    {"id": "all", "name": "All", "description": "Fallback (agent failed)."},
                    {"id": "smb", "name": "SMB", "description": "Placeholder (agent failed)."},
                ],
                "jtbd": [{"id": "jtbd_fallback", "statement": "N/A", "context": str(e), "related_segments": ["All"]}],
                "insights": [
                    {"id": "insight_fallback", "statement": "Agent failed.", "evidence_refs": [], "confidence": "Speculative", "impacted_segments": ["All"]},
                ] * 5,
                "research_gaps": ["Customer insights agent failed; re-run after fix."] * 3,
                "validation_plan": [{"step": 1, "method": "Re-run pipeline", "goal": "Obtain findings_customer.json"}, {"step": 2, "method": "N/A", "goal": "N/A"}, {"step": 3, "method": "N/A", "goal": "N/A"}],
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

    # 5) Tech Feasibility & Delivery Agent (Agent F): findings_feasibility.json (always write something)
    try:
        from agents.feasibility_delivery_agent import run as feasibility_run

        # Best-effort load of requirements findings for richer phasing/complexity context
        req_findings_path = target_dir / "findings_requirements.json"
        try:
            findings_requirements = (
                read_json(req_findings_path) if req_findings_path.exists() else None
            )
        except Exception:
            findings_requirements = None

        feasibility_findings = feasibility_run(context_packet, findings_requirements)
        write_json(target_dir / "findings_feasibility.json", feasibility_findings)
    except Exception as e:
        log.warning("Feasibility & delivery agent failed: %s", e)
        write_json(
            target_dir / "findings_feasibility.json",
            {
                "bundle_id": bundle_name,
                "dependencies": [],
                "constraints": [],
                "complexity": [],
                "phases": {
                    "MVP": {
                        "in_scope": [],
                        "out_of_scope": [],
                        "prerequisites": [],
                    },
                    "V1": {
                        "in_scope": [],
                        "out_of_scope": [],
                        "prerequisites": [],
                    },
                    "V2": {
                        "in_scope": [],
                        "out_of_scope": [],
                        "prerequisites": [],
                    },
                },
                "build_vs_buy_triggers": [],
                "warnings": [str(e)],
            },
        )

    # 6) Placeholders for other artifacts
    _create_placeholders(target_dir)

        # --- Schema validation (Intern 3 hardening) ---
    try:
        from tools.schema_validator import validate_run_outputs
        validation_report = validate_run_outputs(target_dir)
        write_json(target_dir / "schema_validation.json", validation_report)

        # Optional: treat "warnings" in outputs as failure if requested
        warnings_found = False
        for fname in ["findings_metrics.json", "findings_requirements.json"]:
            p = target_dir / fname
            if p.exists():
                data = read_json(p)
                if isinstance(data, dict) and data.get("warnings"):
                    warnings_found = True

        if strict and not validation_report.get("valid", False):
            raise ValueError(f"Schema validation failed. See {target_dir / 'schema_validation.json'}")

        if strict and fail_on_warnings and warnings_found:
            raise ValueError(f"Strict mode: warnings present. See outputs in {target_dir}")
    except Exception as e:
        log.warning("Schema validation step failed: %s", e)
        if strict:
            raise
        
    return str(target_dir)