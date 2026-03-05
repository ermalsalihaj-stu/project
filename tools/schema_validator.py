from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from jsonschema import FormatChecker
from jsonschema.validators import validator_for

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = PROJECT_ROOT / "schemas"


def _schema_path(schema_filename_no_ext: str) -> Path:
    return SCHEMAS_DIR / f"{schema_filename_no_ext}.schema.json"


def load_schema(schema_filename_no_ext: str) -> Dict[str, Any]:
    """
    Loads schemas/<name>.schema.json
    Example: load_schema("findings_metrics") -> schemas/findings_metrics.schema.json
    """
    path = _schema_path(schema_filename_no_ext)
    if not path.exists():
        raise FileNotFoundError(f"Schema not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def validate_instance(instance: Any, schema: Dict[str, Any]) -> List[str]:
    """
    Returns a list of human-readable validation errors.
    Uses Draft version inferred from the schema's $schema.
    """
    Validator = validator_for(schema)
    Validator.check_schema(schema)
    validator = Validator(schema, format_checker=FormatChecker())

    errors = sorted(validator.iter_errors(instance), key=lambda e: (list(e.absolute_path), e.message))
    out: List[str] = []
    for e in errors:
        path = "/".join(str(p) for p in e.absolute_path) or "<root>"
        out.append(f"{path}: {e.message}")
    return out


def validate_json_file(json_path: str | Path, schema_name: str) -> List[str]:
    p = Path(json_path)
    schema = load_schema(schema_name)
    instance = json.loads(p.read_text(encoding="utf-8"))
    return validate_instance(instance, schema)


def validate_run_outputs(run_dir: str | Path) -> Dict[str, Any]:
    """
    Validates known JSON outputs in a run directory.
    If a schema file does not exist yet, that output is SKIPPED (not treated as failure).
    """
    rd = Path(run_dir)

    report: Dict[str, Any] = {
        "run_dir": str(rd),
        "valid": True,
        "files": {},
    }

    targets: List[Tuple[str, str]] = [
        ("findings_metrics.json", "findings_metrics"),
        ("findings_requirements.json", "findings_requirements"),
        ("findings_risk.json", "findings_risk"),
        ("final_recommendation.json", "final_recommendation"),
        ("roadmap.json", "roadmap"),
    ]

    for filename, schema_name in targets:
        fp = rd / filename
        schema_path = _schema_path(schema_name)

        # If schema is not present yet, skip validation for that file
        if not schema_path.exists():
            report["files"][filename] = {
                "valid": None,
                "skipped": True,
                "reason": f"schema missing: {schema_path.name}",
                "errors": [],
            }
            continue

        # If schema exists, the file must exist
        if not fp.exists():
            report["valid"] = False
            report["files"][filename] = {
                "valid": False,
                "skipped": False,
                "errors": ["file missing"],
            }
            continue

        errs = validate_json_file(fp, schema_name)
        ok = len(errs) == 0

        report["files"][filename] = {
            "valid": ok,
            "skipped": False,
            "errors": errs,
        }

        if not ok:
            report["valid"] = False

    return report