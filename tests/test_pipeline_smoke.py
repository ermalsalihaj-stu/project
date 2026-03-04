import json
from pathlib import Path

from orchestration.pipeline import run_pipeline


def test_pipeline_creates_core_outputs(tmp_path: Path):
    # Minimal bundle created inside the test
    b = tmp_path / "bundle_smoke"
    b.mkdir(parents=True, exist_ok=True)

    (b / "bundle_manifest.json").write_text(
        json.dumps(
            {
                "bundle_id": "bundle_smoke",
                "files": {
                    "request": "product_request.md",
                    "tickets": "tickets.json",
                    "customer_notes": "customer_notes.md",
                    "metrics_snapshot": "metrics_snapshot.json",
                    "competitors": "competitors.md",
                },
            }
        ),
        encoding="utf-8",
    )

    (b / "product_request.md").write_text("Smoke request\n", encoding="utf-8")
    (b / "tickets.json").write_text("[]", encoding="utf-8")
    (b / "customer_notes.md").write_text("Notes\n", encoding="utf-8")
    (b / "metrics_snapshot.json").write_text("{}", encoding="utf-8")
    (b / "competitors.md").write_text("Competitors\n", encoding="utf-8")

    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)

    run_pipeline(str(b), out_dir=str(out_dir))

    assert (out_dir / "context_packet.json").exists()
    assert (out_dir / "findings_metrics.json").exists()
    assert (out_dir / "findings_requirements.json").exists()
    assert (out_dir / "findings_feasibility.json").exists()
    assert (out_dir / "backlog.csv").exists()