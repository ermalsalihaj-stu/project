from pathlib import Path

from orchestration.pipeline import run_pipeline


def test_end_to_end_final_outputs(tmp_path: Path):
    project_root = Path(__file__).resolve().parent.parent
    bundle = project_root / "bundles" / "sample_01"
    assert bundle.is_dir(), "bundles/sample_01 not found"

    out_dir = tmp_path / "run_out"
    out_dir.mkdir(parents=True, exist_ok=True)

    run_pipeline(str(bundle), out_dir=str(out_dir), strict=True)

    expected_files = [
        "context_packet.json",
        "findings_customer.json",
        "findings_metrics.json",
        "findings_requirements.json",
        "findings_feasibility.json",
        "findings_risk.json",
        "final_recommendation.json",
        "prd.md",
        "roadmap.json",
        "experiment_plan.md",
        "decision_log.md",
        "backlog.csv",
    ]

    for name in expected_files:
        assert (out_dir / name).exists(), f"Missing expected output: {name}"