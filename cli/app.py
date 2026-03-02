"""CLI for run and validate commands."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Project root is parent of cli/
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _resolve_bundle_path(bundle_arg: str) -> Path:
    """Resolve bundle path to absolute; accept 'bundles/sample_01' or path."""
    p = Path(bundle_arg)
    if not p.is_absolute():
        p = (PROJECT_ROOT / p).resolve()
    if not p.is_dir():
        raise FileNotFoundError(f"Bundle directory not found: {p}")
    return p


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate a bundle and print errors/warnings."""
    from tools.validate_bundle import validate_bundle

    try:
        bundle_path = _resolve_bundle_path(args.bundle)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    errors, warnings = validate_bundle(bundle_path)
    for w in warnings:
        print(f"Warning: {w}", file=sys.stderr)
    for e in errors:
        print(f"Error: {e}", file=sys.stderr)

    if errors:
        print("\nValidation FAILED.", file=sys.stderr)
        return 1
    if warnings:
        print("\nValidation OK (with warnings).")
    else:
        print("Validation OK.")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Run pipeline for a bundle and write artifacts to runs/."""
    from tools.logging_utils import get_logger, setup_logging

    from orchestration.pipeline import run_pipeline

    setup_logging()
    logger = get_logger("cli")

    try:
        bundle_path = _resolve_bundle_path(args.bundle)
    except FileNotFoundError as e:
        logger.error("%s", e)
        return 1

    # Optional: validate first so user gets clear errors
    from tools.validate_bundle import validate_bundle

    errors, _ = validate_bundle(bundle_path)
    if errors:
        logger.error("Bundle validation failed. Fix errors before running.")
        for e in errors:
            logger.error("  %s", e)
        return 1

    try:
        out_dir = run_pipeline(str(bundle_path))
        logger.info("Run complete. Output: %s", out_dir)
        return 0
    except Exception as e:
        logger.exception("Pipeline failed: %s", e)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(prog="main.py", description="AI Product Manager CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run pipeline for a bundle")
    run_parser.add_argument("--bundle", required=True, help="Path to bundle, e.g. bundles/sample_01")
    run_parser.set_defaults(func=cmd_run)

    validate_parser = subparsers.add_parser("validate", help="Validate a bundle")
    validate_parser.add_argument("--bundle", required=True, help="Path to bundle, e.g. bundles/sample_01")
    validate_parser.set_defaults(func=cmd_validate)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
