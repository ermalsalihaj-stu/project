from __future__ import annotations

from datetime import datetime, timezone
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
    """Create placeholder artifacts that are safe to overwrite by writers."""
    # backlog.csv
    backlog_path = out_dir / "backlog.csv"
    if not backlog_path.exists():
        write_text(
            backlog_path,
            "type,id,title,description,priority,epic_id,acceptance_criteria,linked_requirements,dependencies\n",
        )

    # PRD
    prd_path = out_dir / "prd.md"
    if not prd_path.exists():
        write_text(prd_path, "# PRD\n\nPending generation.\n")

    # Experiment plan
    exp_path = out_dir / "experiment_plan.md"
    if not exp_path.exists():
        write_text(exp_path, "# Experiment Plan\n\nPending generation.\n")

    # Decision log
    decision_log_path = out_dir / "decision_log.md"
    if not decision_log_path.exists():
        write_text(decision_log_path, "# Decision Log\n\nPending generation.\n")

    # Roadmap
    roadmap_path = out_dir / "roadmap.json"
    if not roadmap_path.exists():
        write_json(
            roadmap_path,
            {
                "mvp": [],
                "v1": [],
                "v2": [],
                "warnings": ["placeholder roadmap"],
            },
        )


def run_pipeline(
    bundle_path: str,
    out_dir: str | None = None,
    strict: bool = False,
    fail_on_warnings: bool = False,
) -> str:
    """
    Run the pipeline for the given bundle:
      - Intake Agent -> context_packet.json (+ evidence_index.json)
      - Metrics Agent -> findings_metrics.json
      - Competitive & Positioning Agent -> findings_competition.json
      - Customer Insights Agent -> findings_customer.json
      - UX/Requirements Agent -> findings_requirements.json
      - Backlog writer -> backlog.csv
      - Tech Feasibility & Delivery Agent -> findings_feasibility.json
      - Risk / Guardrails Agent -> findings_risk.json
      - Lead PM Agent -> final_recommendation.json
      - Artifact writers -> prd.md, roadmap.json, experiment_plan.md, decision_log.md

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

    # 1) Intake Agent: context_packet.json + evidence_index.json
    try:
        from agents.intake_context_agent import run as intake_run

        intake_run(bundle_path, target_dir)
    except Exception as e:
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

    # Keep this defined for downstream agents even if requirements fail
    req_findings = None

    # 2) Metrics & Analytics Agent (Agent D): findings_metrics.json
    try:
        from agents.metrics_analytics_agent import run as metrics_run

        findings_metrics = metrics_run(context_packet)
        write_json(target_dir / "findings_metrics.json", findings_metrics)
    except Exception as e:
        log.warning("Metrics analytics agent failed: %s", e)
        findings_metrics = {
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
        }
        write_json(target_dir / "findings_metrics.json", findings_metrics)

    # 2b) Competitive & Positioning Agent (Agent C): findings_competition.json
    try:
        from agents.competitive_positioning_agent import run as comp_run

        findings_competition = comp_run(context_packet)
        write_json(target_dir / "findings_competition.json", findings_competition)
    except Exception as e:
        log.warning("Competitive & positioning agent failed: %s", e)
        findings_competition = {
            "bundle_id": bundle_name,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "competitors": [],
            "parity_opportunities": [],
            "differentiation_opportunities": [],
            "recommended_positioning": "",
            "messaging_pillars": [],
            "research_gaps": [
                "Competitive & positioning agent failed; collect competitor data and re-run."
            ],
            "warnings": [str(e)],
        }
        write_json(target_dir / "findings_competition.json", findings_competition)

    # 2c) Customer Insights Agent (Agent B): findings_customer.json
    try:
        from agents.customer_insights_agent import run as customer_insights_run

        findings_customer = customer_insights_run(context_packet)
        write_json(target_dir / "findings_customer.json", findings_customer)
    except Exception as e:
        log.warning("Customer insights agent failed: %s", e)
        findings_customer = {
            "bundle_id": bundle_name,
            "segments": [
                {"id": "all", "name": "All", "description": "Fallback (agent failed)."},
                {"id": "smb", "name": "SMB", "description": "Placeholder (agent failed)."},
            ],
            "jtbd": [
                {
                    "id": "jtbd_fallback",
                    "statement": "N/A",
                    "context": str(e),
                    "related_segments": ["All"],
                }
            ],
            "insights": [
                {
                    "id": "insight_fallback_1",
                    "statement": "Agent failed.",
                    "evidence_refs": [],
                    "confidence": "Speculative",
                    "impacted_segments": ["All"],
                },
                {
                    "id": "insight_fallback_2",
                    "statement": "Agent failed.",
                    "evidence_refs": [],
                    "confidence": "Speculative",
                    "impacted_segments": ["All"],
                },
                {
                    "id": "insight_fallback_3",
                    "statement": "Agent failed.",
                    "evidence_refs": [],
                    "confidence": "Speculative",
                    "impacted_segments": ["All"],
                },
                {
                    "id": "insight_fallback_4",
                    "statement": "Agent failed.",
                    "evidence_refs": [],
                    "confidence": "Speculative",
                    "impacted_segments": ["All"],
                },
                {
                    "id": "insight_fallback_5",
                    "statement": "Agent failed.",
                    "evidence_refs": [],
                    "confidence": "Speculative",
                    "impacted_segments": ["All"],
                },
            ],
            "research_gaps": [
                "Customer insights agent failed; re-run after fix.",
                "Customer insights agent failed; re-run after fix.",
                "Customer insights agent failed; re-run after fix.",
            ],
            "validation_plan": [
                {"step": 1, "method": "Re-run pipeline", "goal": "Obtain findings_customer.json"},
                {"step": 2, "method": "Review logs", "goal": "Find root cause"},
                {"step": 3, "method": "Re-test", "goal": "Verify output"},
            ],
        }
        write_json(target_dir / "findings_customer.json", findings_customer)

    # 3) UX & Requirements Agent (Agent E): findings_requirements.json
    try:
        from agents.ux_requirements_agent import run as req_run

        req_findings = req_run(context_packet)
        write_json(target_dir / "findings_requirements.json", req_findings)

        # 4) Backlog CSV generator from req_findings["backlog"]
        from tools.backlog_writer import write_backlog_csv

        write_backlog_csv(req_findings, target_dir / "backlog.csv")
    except Exception as e:
        log.warning("UX requirements agent failed: %s", e)
        req_findings = {
            "bundle_id": bundle_name,
            "summary": "",
            "journeys": [],
            "requirements": [],
            "edge_cases": [],
            "backlog": {"epics": [], "stories": []},
            "warnings": [str(e)],
        }
        write_json(target_dir / "findings_requirements.json", req_findings)
        _create_placeholders(target_dir)

    # 5) Tech Feasibility & Delivery Agent (Agent F): findings_feasibility.json
    try:
        from agents.feasibility_delivery_agent import run as feasibility_run

        feasibility_findings = feasibility_run(context_packet, req_findings)
        write_json(target_dir / "findings_feasibility.json", feasibility_findings)
    except Exception as e:
        log.warning("Feasibility & delivery agent failed: %s", e)
        feasibility_findings = {
            "bundle_id": bundle_name,
            "dependencies": [],
            "constraints": [],
            "complexity": [],
            "phases": {
                "MVP": {"in_scope": [], "out_of_scope": [], "prerequisites": []},
                "V1": {"in_scope": [], "out_of_scope": [], "prerequisites": []},
                "V2": {"in_scope": [], "out_of_scope": [], "prerequisites": []},
            },
            "build_vs_buy_triggers": [],
            "warnings": [str(e)],
        }
        write_json(target_dir / "findings_feasibility.json", feasibility_findings)

    # 5b) Risk / Guardrails Agent (Agent G): findings_risk.json
    try:
        from agents.risk_guardrails_agent import run as risk_run

        risk_findings = risk_run(context_packet, findings_requirements=req_findings)
        write_json(target_dir / "findings_risk.json", risk_findings)
    except Exception as e:
        log.warning("Risk guardrails agent failed: %s", e)
        risk_findings = {
            "bundle_id": bundle_name,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "gating_decision": "Validate first",
            "risks": [],
            "required_mitigations": [],
            "policy_pack": {"version": "unknown", "applied_rule_ids": []},
            "policy_evaluation": [],
            "warnings": [str(e)],
        }
        write_json(target_dir / "findings_risk.json", risk_findings)

    # 5c) Lead PM Agent: synthesize all findings -> final_recommendation.json
    all_findings = {
        "context_packet": context_packet,
        "findings_customer": findings_customer,
        "findings_metrics": findings_metrics,
        "findings_requirements": req_findings or {},
        "findings_feasibility": feasibility_findings,
        "findings_risk": risk_findings,
        "findings_competition": findings_competition,
    }

    try:
        from agents.lead_pm_agent import run as lead_pm_run

        final_rec = lead_pm_run(all_findings)
        write_json(target_dir / "final_recommendation.json", final_rec)
    except Exception as e:
        log.warning("Lead PM agent failed: %s", e)
        final_rec = {
            "bundle_id": bundle_name,
            "executive_summary": "Lead PM synthesis failed; re-run pipeline after fixing agents.",
            "problem_statement": "",
            "recommended_direction": "Validate first",
            "gating_decision": "Validate first",
            "top_opportunities": [],
            "top_risks": [str(e)],
            "tradeoffs": [],
            "assumptions": [],
            "open_questions": ["Re-run pipeline to generate final_recommendation.json."],
            "recommended_scope_now": [],
            "recommended_scope_later": [],
            "success_metrics": [],
            "decision_rationale": [f"Lead PM agent failed: {e}"],
            "warnings": [str(e)],
        }
        write_json(target_dir / "final_recommendation.json", final_rec)

    # 6) Final artifact writers (PRD, roadmap, experiment plan, decision log)
    try:
        from tools.prd_writer import write_prd
        from tools.roadmap_writer import write_roadmap
        from tools.experiment_writer import write_experiment_plan
        from tools.decision_log_writer import write_decision_log

        write_prd(
            final_rec,
            findings_customer=findings_customer,
            findings_metrics=findings_metrics,
            findings_requirements=req_findings or {},
            findings_feasibility=feasibility_findings,
            findings_risk=risk_findings,
            out_path=target_dir / "prd.md",
        )
        write_roadmap(
            final_rec,
            findings_feasibility=feasibility_findings,
            findings_risk=risk_findings,
            out_path=target_dir / "roadmap.json",
        )
        write_experiment_plan(
            final_rec,
            findings_customer=findings_customer,
            findings_metrics=findings_metrics,
            findings_risk=risk_findings,
            out_path=target_dir / "experiment_plan.md",
        )
        write_decision_log(
            final_rec,
            findings_risk=risk_findings,
            findings_feasibility=feasibility_findings,
            findings_competition=findings_competition,
            out_path=target_dir / "decision_log.md",
        )
    except Exception as e:
        log.warning("Artifact writers failed: %s", e)

        if not (target_dir / "prd.md").exists():
            write_text(target_dir / "prd.md", f"# PRD\n\nWriter fallback.\n\nError: {e}\n")

        if not (target_dir / "roadmap.json").exists():
            write_json(
                target_dir / "roadmap.json",
                {
                    "mvp": [],
                    "v1": [],
                    "v2": [],
                    "warnings": [str(e)],
                },
            )

        if not (target_dir / "experiment_plan.md").exists():
            write_text(
                target_dir / "experiment_plan.md",
                f"# Experiment Plan\n\nWriter fallback.\n\nError: {e}\n",
            )

        if not (target_dir / "decision_log.md").exists():
            write_text(
                target_dir / "decision_log.md",
                f"# Decision Log\n\nWriter fallback.\n\nError: {e}\n",
            )

    # 7) Ensure final artifacts and backlog exist where needed
    _create_placeholders(target_dir)

    # --- Schema validation ---
    try:
        from tools.schema_validator import validate_run_outputs

        validation_report = validate_run_outputs(target_dir)
        write_json(target_dir / "schema_validation.json", validation_report)

        # Optional: treat "warnings" in outputs as failure if requested
        warnings_found = False
        for fname in [
            "findings_metrics.json",
            "findings_competition.json",
            "findings_customer.json",
            "findings_requirements.json",
            "findings_feasibility.json",
            "findings_risk.json",
            "final_recommendation.json",
            "roadmap.json",
        ]:
            p = target_dir / fname
            if p.exists():
                try:
                    data = read_json(p)
                    if isinstance(data, dict) and data.get("warnings"):
                        warnings_found = True
                except Exception:
                    # Non-JSON or malformed file should be caught by schema validation if relevant
                    pass

        if strict and not validation_report.get("valid", False):
            raise ValueError(f"Schema validation failed. See {target_dir / 'schema_validation.json'}")

        if strict and fail_on_warnings and warnings_found:
            raise ValueError(f"Strict mode: warnings present. See outputs in {target_dir}")
    except Exception as e:
        log.warning("Schema validation step failed: %s", e)
        if strict:
            raise

    # Optional: automatically post run summary to PR when GitHub env vars are set
    import os
    if all(os.environ.get(k) for k in ("GITHUB_TOKEN", "GITHUB_REPO", "GITHUB_PR_NUMBER")):
        try:
            from integrations.github.pr_poster import build_pr_message, post_pr_comment
            post_pr_comment(
                os.environ["GITHUB_REPO"],
                int(os.environ["GITHUB_PR_NUMBER"]),
                build_pr_message(target_dir),
                os.environ["GITHUB_TOKEN"],
                update_if_exists=True,
            )
            log.info("Posted run summary to PR")
        except Exception as e:
            log.warning("GitHub PR post failed (optional): %s", e)

    return str(target_dir)