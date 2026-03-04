from pathlib import Path

from orchestration.pipeline import run_pipeline
from tools.schema_validator import validate_run_outputs


def test_outputs_match_schemas(tmp_path: Path):
    project_root = Path(__file__).resolve().parent.parent
    bundle = project_root / "bundles" / "sample_01"
    assert bundle.is_dir(), "bundles/sample_01 not found"

    out_dir = tmp_path / "run_out"
    out_dir.mkdir(parents=True, exist_ok=True)

    run_pipeline(str(bundle), out_dir=str(out_dir), strict=True)

    report = validate_run_outputs(out_dir)
    assert report["valid"] is True, f"Schema errors: {report}"