"""CLI for run and validate commands."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Project root is parent of cli/
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Load .env from project root so GITHUB_* are available for post-pr
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass


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
        out_dir = run_pipeline(
            str(bundle_path),
            strict=bool(getattr(args, "strict", False)),
            fail_on_warnings=bool(getattr(args, "fail_on_warnings", False)),
        )
        logger.info("Run complete. Output: %s", out_dir)
        return 0
    except Exception as e:
        logger.exception("Pipeline failed: %s", e)
        return 1


def _resolve_run_dir(run_dir_arg: str) -> Path:
    """Resolve run directory to absolute; accept runs/2026-03-05_1638_sample_01 or path."""
    p = Path(run_dir_arg)
    if not p.is_absolute():
        p = (PROJECT_ROOT / p).resolve()
    if not p.is_dir():
        raise FileNotFoundError(f"Run directory not found: {p}")
    return p


def cmd_post_pr(args: argparse.Namespace) -> int:
    """Post run summary as a comment on a GitHub PR (for Intern 3 / synthesis output)."""
    from integrations.github.pr_poster import build_pr_message, post_pr_comment

    try:
        run_path = _resolve_run_dir(args.run_dir)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    token = getattr(args, "token", None) or os.environ.get("GITHUB_TOKEN")
    repo = getattr(args, "repo", None) or os.environ.get("GITHUB_REPO")
    pr_number = getattr(args, "pr_number", None)
    if pr_number is None:
        raw = os.environ.get("GITHUB_PR_NUMBER")
        pr_number = int(raw) if raw else None

    if not token:
        print("Error: GITHUB_TOKEN not set (env or --token)", file=sys.stderr)
        return 1
    if not repo:
        print("Error: GITHUB_REPO not set (env or --repo), e.g. owner/repo", file=sys.stderr)
        return 1
    if pr_number is None:
        print("Error: GITHUB_PR_NUMBER not set (env or --pr)", file=sys.stderr)
        return 1

    try:
        body = build_pr_message(run_path)
        result = post_pr_comment(repo, int(pr_number), body, token, update_if_exists=not getattr(args, "new_comment", False))
        print(f"Comment posted/updated: {result.get('html_url', result)}")
        return 0
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error posting comment: {e}", file=sys.stderr)
        return 1


def cmd_ingest_jira(args: argparse.Namespace) -> int:
    """Ingest Jira (JQL) into a local bundle; then run can use that bundle."""
    from tools.logging_utils import get_logger, setup_logging

    setup_logging()
    log = get_logger("cli")

    jql = getattr(args, "jql", None) or os.environ.get("JIRA_JQL", "")
    if not jql.strip():
        log.error("JQL required: set JIRA_JQL (env) or pass --jql")
        return 1

    try:
        from integrations.jira.ingest import ingest_jira_to_bundle

        bundle_path = ingest_jira_to_bundle(
            jql=jql.strip(),
            project_key=getattr(args, "project", None) or os.environ.get("JIRA_PROJECT"),
            max_issues=int(getattr(args, "max_results", 500)),
            include_comment_notes=bool(getattr(args, "comments", True)),
            _issues_override=None,
        )
        log.info("Bundle created: %s", bundle_path)
        print(bundle_path.resolve())
        return 0
    except ValueError as e:
        log.error("%s", e)
        return 1
    except Exception as e:
        log.exception("Ingest failed: %s", e)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(prog="main.py", description="AI Product Manager CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run pipeline for a bundle")
    run_parser.add_argument("--bundle", required=True, help="Path to bundle, e.g. bundles/sample_01")
    run_parser.add_argument("--strict", action="store_true", help="Fail if output JSON does not match schemas")
    run_parser.add_argument("--fail-on-warnings", action="store_true", help="(Strict only) Fail if outputs contain warnings[]")
    run_parser.set_defaults(func=cmd_run)

    validate_parser = subparsers.add_parser("validate", help="Validate a bundle")
    validate_parser.add_argument("--bundle", required=True, help="Path to bundle, e.g. bundles/sample_01")
    validate_parser.set_defaults(func=cmd_validate)

    ingest_jira_parser = subparsers.add_parser(
        "ingest-jira",
        help="Ingest Jira issues (JQL) into a local bundle (uses JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN, or JIRA_JQL)",
    )
    ingest_jira_parser.add_argument("--jql", default=None, help="JQL query (default: JIRA_JQL env)")
    ingest_jira_parser.add_argument("--project", default=None, help="Project key for bundle name (default: from JQL)")
    ingest_jira_parser.add_argument("--max-results", type=int, default=500, help="Max issues to fetch")
    ingest_jira_parser.add_argument("--no-comments", dest="comments", action="store_false", help="Skip customer_notes from comments")
    ingest_jira_parser.set_defaults(func=cmd_ingest_jira)

    post_pr_parser = subparsers.add_parser(
        "post-pr",
        help="Post run summary as a PR comment (uses GITHUB_TOKEN, GITHUB_REPO, GITHUB_PR_NUMBER)",
    )
    post_pr_parser.add_argument("--run-dir", required=True, help="Run directory, e.g. runs/2026-03-05_1638_sample_01")
    post_pr_parser.add_argument("--new", dest="new_comment", action="store_true", help="Always post a new comment (default: update existing AIPM comment if present)")
    post_pr_parser.add_argument("--token", default=None, help="GitHub token (default: GITHUB_TOKEN)")
    post_pr_parser.add_argument("--repo", default=None, help="Repo owner/name (default: GITHUB_REPO)")
    post_pr_parser.add_argument("--pr", type=int, default=None, dest="pr_number", help="PR number (default: GITHUB_PR_NUMBER)")
    post_pr_parser.set_defaults(func=cmd_post_pr)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
