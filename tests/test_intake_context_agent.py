import json
from pathlib import Path

from agents.intake_context_agent import run


def test_run_creates_context_packet(tmp_path: Path):
    # krijo bundle minimal (edhe pa tickets)
    bundle_dir = tmp_path / "sample_00"
    bundle_dir.mkdir(parents=True, exist_ok=True)

    (bundle_dir / "bundle_manifest.json").write_text(json.dumps({
        "bundle_id": "sample_00",
        "files": {
            "request": "product_request.md",
            "tickets": "tickets.json",
            "customer_notes": "customer_notes.md",
            "metrics_snapshot": "metrics_snapshot.json",
            "competitors": "competitors.md"
        }
    }), encoding="utf-8")

    (bundle_dir / "product_request.md").write_text("Build something minimal.\n", encoding="utf-8")

    out_dir = tmp_path / "run_out"
    out_dir.mkdir(parents=True, exist_ok=True)

    cp = run(bundle_dir, out_dir=out_dir)

    assert (out_dir / "context_packet.json").exists()
    assert cp["bundle_id"] == "sample_00"
    assert "warnings" in cp