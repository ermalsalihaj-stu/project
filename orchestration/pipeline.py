"""Orchestration skeleton: run pipeline for a bundle and write artifacts."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from tools.io_utils import read_json, write_json, write_text

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

    # CSV placeholder
    backlog_path = out_dir / "backlog.csv"
    if not backlog_path.exists():
        write_text(backlog_path, "")


def run_pipeline(bundle_path: str, out_dir: str | None = None) -> str:
    """
    Run the pipeline for the given bundle: Intake Agent + placeholder artifacts.
    Creates runs/YYYY-MM-DD_HHMM_<bundle_name>/ and returns its path.
    """
    bundle_path = Path(bundle_path).resolve()
    if not bundle_path.is_dir():
        raise FileNotFoundError(f"Bundle not found: {bundle_path}")

    bundle_name = bundle_path.name
    run_name = _run_dir_name(bundle_name)
    target_dir = RUNS_DIR / run_name if out_dir is None else Path(out_dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    # Intake Agent (Intern 3): context_packet.json + evidence_index.json
    try:
        from agents.intake_context_agent import run as intake_run

        intake_run(bundle_path, target_dir)
    except Exception as e:
        # If intake not ready, write placeholder and message
        from tools.io_utils import write_json as _wj

        _wj(
            target_dir / "context_packet.json",
            {
                "bundle_id": bundle_name,
                "_message": "Intake agent not implemented yet or failed",
                "_error": str(e),
            },
        )
        from tools.logging_utils import get_logger

        get_logger("pipeline").warning("Intake agent failed: %s; wrote placeholder context_packet.json", e)

    # Metrics & Analytics Agent (Agent D): findings_metrics.json
    context_path = target_dir / "context_packet.json"
    if context_path.exists():
        try:
            context_packet = read_json(context_path)
            from agents.metrics_analytics_agent import run as metrics_run

            findings = metrics_run(context_packet)
            write_json(target_dir / "findings_metrics.json", findings)
        except Exception as e:
            from tools.logging_utils import get_logger

            get_logger("pipeline").warning("Metrics analytics agent failed: %s", e)

    # Placeholders for other artifacts
    _create_placeholders(target_dir)

    return str(target_dir)
