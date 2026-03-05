from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, Optional

def _safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip() or default

def _first(items: Any) -> Optional[Dict[str, Any]]:
    if isinstance(items, list) and items:
        first = items[0]
        if isinstance(first, dict):
            return first
    return None

def write_prd(
    final_recommendation: Dict[str, Any],
    findings_customer: Dict[str, Any] | None,
    findings_metrics: Dict[str, Any] | None,
    findings_requirements: Dict[str, Any] | None,
    findings_feasibility: Dict[str, Any] | None,
    findings_risk: Dict[str, Any] | None,
    out_path: str | Path,
) -> None:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    customer = findings_customer or {}
    metrics = findings_metrics or {}
    reqs = findings_requirements or {}
    feasibility = findings_feasibility or {}
    risk = findings_risk or {}

    bundle_id = _safe_str(final_recommendation.get("bundle_id"), "unknown")
    feature_area = _safe_str(metrics.get("feature_area"), "Product")

    exec_summary = _safe_str(final_recommendation.get("executive_summary"))
    problem_statement = _safe_str(final_recommendation.get("problem_statement"))
    recommended_direction = _safe_str(final_recommendation.get("recommended_direction"))
    gating_decision = _safe_str(final_recommendation.get("gating_decision"))
    success_metrics = final_recommendation.get("success_metrics") or []

    segments = customer.get("segments") or []
    jtbd_list = customer.get("jtbd") or []

    requirements = reqs.get("requirements") or []
    edge_cases = reqs.get("edge_cases") or []

    goals = metrics.get("goals") or []

    risks = risk.get("risks") or []
    mitigations = risk.get("required_mitigations") or []

    phases = feasibility.get("phases") or {}

    lines: list[str] = []

    lines.append(f"# PRD – {feature_area} ({bundle_id})")
    lines.append("")

    lines.append("## Background / context")
    if exec_summary:
        lines.append(exec_summary)
    else:
        lines.append(
            "This PRD summarizes the opportunity, scope, and risks for the current bundle."
        )
    lines.append("")

    lines.append("## Problem")
    if problem_statement:
        lines.append(problem_statement)
    else:
        lines.append(
            "We need a clearer articulation of the user and business problem; the current inputs are thin."
        )
    lines.append("")

    lines.append("## User segments")
    if segments:
        for s in segments:
            name = _safe_str(s.get("name"), "Segment")
            desc = _safe_str(s.get("description"), "")
            lines.append(f"- **{name}** – {desc}")
    else:
        lines.append("- **All users** – Fallback segment from limited customer input.")
    lines.append("")

    lines.append("## JTBD / user pain")
    if jtbd_list:
        for j in jtbd_list:
            stmt = _safe_str(j.get("statement"))
            ctx = _safe_str(j.get("context"))
            if stmt:
                lines.append(f"- **Job:** {stmt}")
                if ctx:
                    lines.append(f"  - Context: {ctx}")
    else:
        lines.append(
            "- Users need a more reliable, understandable experience for this flow; existing inputs only hint at the job-to-be-done."
        )
    lines.append("")

    lines.append("## Goals")
    if goals:
        for g in goals:
            lines.append(f"- {g}")
    else:
        lines.append(
            "- Clarify and de-risk the core experience.\n- Improve completion and satisfaction metrics for the primary flow."
        )
    lines.append("")

    lines.append("## Non-goals")
    non_goals = final_recommendation.get("recommended_scope_later") or []
    if non_goals:
        for item in non_goals:
            lines.append(f"- {item}")
    else:
        lines.append(
            "- Full redesign of adjacent products.\n- Long-term speculative bets that are not tied to the core flow."
        )
    lines.append("")

    lines.append("## Requirements")
    if requirements:
        for r in requirements:
            rid = _safe_str(r.get("id"))
            title = _safe_str(r.get("title"))
            priority = _safe_str(r.get("priority"), "Must")
            stmt = _safe_str(r.get("statement"))
            lines.append(f"- **{rid} – {title}** ({priority})")
            if stmt:
                lines.append(f"  - {stmt}")
    else:
        lines.append(
            "- Requirements will be refined; current requirements agent output was unavailable."
        )
    lines.append("")

    lines.append("## Edge cases")
    if edge_cases:
        for ec in edge_cases:
            eid = _safe_str(ec.get("id"))
            desc = _safe_str(ec.get("description"))
            cat = _safe_str(ec.get("category"), "other")
            lines.append(f"- **{eid}** ({cat}) – {desc}")
    else:
        lines.append("- Edge cases are not yet enumerated; see tickets and support notes for candidates.")
    lines.append("")

    lines.append("## Risks / mitigations")
    if risks:
        for r_item in risks:
            desc = _safe_str(r_item.get("description") or r_item.get("source_risk"))
            sev = _safe_str(r_item.get("severity"), "medium")
            lines.append(f"- **Risk ({sev})** – {desc}")
    else:
        lines.append("- No structured risks available; treat this as a gap and review risk findings.")
    if mitigations:
        lines.append("")
        lines.append("**Mitigations required**")
        for m in mitigations:
            lines.append(f"- {m}")
    lines.append("")

    lines.append("## Success metrics")
    if success_metrics:
        for m in success_metrics:
            lines.append(f"- {m}")
    else:
        ns = _first(metrics.get("input_metrics") or [])
        if ns and ns.get("name"):
            lines.append(f"- {ns.get('name')}")
        else:
            lines.append("- Define at least one primary success metric and 2–3 guardrails.")
    lines.append("")

    lines.append("## Rollout notes")
    if phases:
        for phase_name in ("MVP", "V1", "V2"):
            phase = phases.get(phase_name) or {}
            in_scope = phase.get("in_scope") or []
            if in_scope:
                lines.append(f"**{phase_name} – in scope**")
                for item in in_scope:
                    lines.append(f"- {item}")
    if gating_decision or recommended_direction:
        lines.append("")
        lines.append(
            f"Gating decision: **{gating_decision or 'Validate first'}**. "
            f"Direction: {recommended_direction or 'See final_recommendation.json for narrative.'}"
        )

    out.write_text("\n".join(lines), encoding="utf-8")

