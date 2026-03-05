"""
Lead PM Agent: synthesis of all findings_*.json into a single product decision.

Consumes: findings_customer, findings_metrics, findings_requirements,
findings_feasibility, findings_risk.
Produces: final_recommendation.json with direction, scope, trade-offs, rationale.

Logic:
- High risk → recommendation not aggressive.
- High complexity (feasibility) → narrow MVP scope.
- Insights mostly Speculative → "Validate first".
- Weak metrics but strong opportunity → "Proceed with mitigations".
"""
from __future__ import annotations

from typing import Any


def run(all_findings: dict) -> dict:
    """
    Run the Lead PM agent.
    Input: all_findings = {
      "findings_customer": {...},
      "findings_metrics": {...},
      "findings_requirements": {...},
      "findings_feasibility": {...},
      "findings_risk": {...},
    }
    Missing keys are tolerated; agent uses what is present.
    Returns: dict conforming to final_recommendation.schema.json.
    """
    customer = all_findings.get("findings_customer") or {}
    metrics = all_findings.get("findings_metrics") or {}
    requirements = all_findings.get("findings_requirements") or {}
    feasibility = all_findings.get("findings_feasibility") or {}
    risk = all_findings.get("findings_risk") or {}

    bundle_id = (
        risk.get("bundle_id")
        or feasibility.get("bundle_id")
        or requirements.get("bundle_id")
        or metrics.get("bundle_id")
        or customer.get("bundle_id")
        or "unknown"
    )

    # Derive signals for decision logic
    gating_from_risk = risk.get("gating_decision") or "Validate first"
    risk_high = gating_from_risk in ("Do not pursue", "Validate first")
    risks_list = risk.get("risks") or []
    has_critical = any((r.get("severity") or "").lower() in ("high", "critical") for r in risks_list)

    complexity_list = feasibility.get("complexity") or []
    has_high_complexity = any((c.get("bucket") or "").lower() == "high" for c in complexity_list)
    phases = feasibility.get("phases") or {}
    mvp_scope = phases.get("MVP") or {}
    in_scope_now = mvp_scope.get("in_scope") or []
    out_of_scope = mvp_scope.get("out_of_scope") or []
    v1_scope = (phases.get("V1") or {}).get("in_scope") or []

    insights = customer.get("insights") or []
    validated_count = sum(1 for i in insights if (i.get("confidence") or "").lower() == "validated")
    speculative_count = sum(1 for i in insights if (i.get("confidence") or "").lower() == "speculative")
    mostly_speculative = len(insights) > 0 and speculative_count >= validated_count and speculative_count >= 2

    metrics_issues = metrics.get("issues") or []
    metrics_weak = any(
        (isinstance(x, dict) and (x.get("type") or "").lower() == "missing_baselines")
        or (isinstance(x, str) and "baseline" in x.lower())
        for x in metrics_issues
    )
    goals = metrics.get("goals") or []
    north_star = metrics.get("north_star_metric") or {}
    opportunity_strong = bool(goals or north_star.get("name"))

    # Recommended direction and gating
    recommended_direction, gating_decision = _decide_direction_and_gating(
        risk_high=risk_high,
        has_critical=has_critical,
        has_high_complexity=has_high_complexity,
        mostly_speculative=mostly_speculative,
        metrics_weak=metrics_weak,
        opportunity_strong=opportunity_strong,
        gating_from_risk=gating_from_risk,
    )

    # Executive summary and problem statement
    feature_area = metrics.get("feature_area") or "Product scope"
    summary = requirements.get("summary") or ""
    problem_statement = _build_problem_statement(
        feature_area=feature_area,
        summary=summary,
        customer=customer,
        risk=risk,
    )
    executive_summary = _build_executive_summary(
        recommended_direction=recommended_direction,
        gating_decision=gating_decision,
        problem_statement=problem_statement,
        has_high_complexity=has_high_complexity,
    )

    # Top opportunities (from goals, JTBD, requirements)
    top_opportunities = _top_opportunities(customer, metrics, requirements)
    top_risks = _top_risks(risk, feasibility)
    tradeoffs = _tradeoffs(feasibility, risk, metrics)
    assumptions = _assumptions(customer, metrics, feasibility)
    open_questions = _open_questions(customer, risk, requirements)

    # Scope now vs later (from feasibility phases + complexity)
    recommended_scope_now = _scope_now(in_scope_now, has_high_complexity, requirements)
    recommended_scope_later = _scope_later(out_of_scope, v1_scope, requirements)

    # Success metrics (from findings_metrics)
    success_metrics = _success_metrics(metrics)

    # Rationale
    decision_rationale = _decision_rationale(
        gating_decision=gating_decision,
        risk_high=risk_high,
        has_high_complexity=has_high_complexity,
        mostly_speculative=mostly_speculative,
        metrics_weak=metrics_weak,
        opportunity_strong=opportunity_strong,
        risk=risk,
    )

    return {
        "bundle_id": bundle_id,
        "executive_summary": executive_summary,
        "problem_statement": problem_statement,
        "recommended_direction": recommended_direction,
        "gating_decision": gating_decision,
        "top_opportunities": top_opportunities,
        "top_risks": top_risks,
        "tradeoffs": tradeoffs,
        "assumptions": assumptions,
        "open_questions": open_questions,
        "recommended_scope_now": recommended_scope_now,
        "recommended_scope_later": recommended_scope_later,
        "success_metrics": success_metrics,
        "decision_rationale": decision_rationale,
    }


def _decide_direction_and_gating(
    risk_high: bool,
    has_critical: bool,
    has_high_complexity: bool,
    mostly_speculative: bool,
    metrics_weak: bool,
    opportunity_strong: bool,
    gating_from_risk: str,
) -> tuple[str, str]:
    """Recommend direction and gating; do not be aggressive if risk is high."""
    if risk_high or has_critical:
        direction = "Address risks and validations before scaling scope; prioritize mitigations and clarity."
        gating = "Validate first" if gating_from_risk == "Do not pursue" else gating_from_risk
        return (direction, gating)
    if mostly_speculative:
        direction = "Validate customer and segment assumptions (interviews, surveys) before committing to build."
        return (direction, "Validate first")
    if has_high_complexity:
        direction = "Proceed with a narrow MVP; phase delivery and defer non-essential scope to V1/V2."
        gating = "Proceed with mitigations" if opportunity_strong else "Validate first"
        return (direction, gating)
    if metrics_weak and opportunity_strong:
        direction = "Proceed with mitigations: establish baselines and instrumentation as you build."
        return (direction, "Proceed with mitigations")
    if opportunity_strong:
        direction = "Proceed with clear success metrics and phased scope; monitor guardrails."
        return (direction, gating_from_risk if gating_from_risk in ("Proceed", "Proceed with mitigations") else "Proceed with mitigations")
    direction = "Gather more evidence (customer and metrics) before committing to scope."
    return (direction, "Validate first")


def _build_problem_statement(
    feature_area: str, summary: str, customer: dict, risk: dict
) -> str:
    """Single problem statement from findings."""
    jtbd = (customer.get("jtbd") or [])[:1]
    jtbd_stmt = jtbd[0].get("statement", "") if jtbd else ""
    risk_desc = (risk.get("risks") or [])[:1]
    risk_desc = risk_desc[0].get("description", "") if risk_desc else ""
    parts = [f"Scope: {feature_area}."]
    if summary:
        parts.append(summary[:400])
    if jtbd_stmt:
        parts.append(f"Key job: {jtbd_stmt[:200]}.")
    if risk_desc:
        parts.append(f"Risks to address: {risk_desc[:150]}.")
    return " ".join(parts)[:800]


def _build_executive_summary(
    recommended_direction: str,
    gating_decision: str,
    problem_statement: str,
    has_high_complexity: bool,
) -> str:
    """2–4 sentence executive summary."""
    parts = [
        f"Recommendation: {recommended_direction}",
        f"Gating decision: {gating_decision}.",
    ]
    if has_high_complexity:
        parts.append("MVP scope has been narrowed due to high complexity; phased delivery recommended.")
    return " ".join(parts)[:600]


def _top_opportunities(customer: dict, metrics: dict, requirements: dict) -> list[str]:
    """From goals, JTBD, and requirements."""
    out: list[str] = []
    for g in (metrics.get("goals") or [])[:3]:
        if isinstance(g, str):
            out.append(g)
    for j in (customer.get("jtbd") or [])[:2]:
        st = j.get("statement") or ""
        if st:
            out.append(st[:120] + ("..." if len(st) > 120 else ""))
    for r in (requirements.get("requirements") or [])[:2]:
        t = r.get("title") or ""
        if t:
            out.append(t)
    return out[:8] if out else ["Improve checkout and billing clarity", "Reduce drop-off and support load"]


def _top_risks(risk: dict, feasibility: dict) -> list[str]:
    """From findings_risk and feasibility constraints."""
    out: list[str] = []
    for r in (risk.get("risks") or [])[:5]:
        desc = r.get("description") or r.get("source_risk") or ""
        if desc:
            out.append(desc[:150])
    for c in (feasibility.get("constraints") or [])[:2]:
        d = c.get("description") or ""
        if d:
            out.append(d[:120])
    return out[:8] if out else ["Risks to be validated from risk agent output."]


def _tradeoffs(feasibility: dict, risk: dict, metrics: dict) -> list[str]:
    """Trade-offs between scope, time, risk."""
    out: list[str] = []
    complexity = feasibility.get("complexity") or []
    for c in complexity[:3]:
        if (c.get("bucket") or "").lower() == "high":
            out.append(f"High complexity in {c.get('topic', 'scope')}: narrow MVP or extend timeline.")
    mitigations = risk.get("required_mitigations") or []
    for m in mitigations[:2]:
        if isinstance(m, str):
            out.append(f"Mitigation required: {m[:100]}.")
    if metrics.get("issues"):
        out.append("Metrics baselines missing: proceed with instrumentation plan or accept limited measurement at launch.")
    return out[:6] if out else ["Scope vs. time: phased delivery balances both."]


def _assumptions(customer: dict, metrics: dict, feasibility: dict) -> list[str]:
    """Assumptions to validate or document."""
    out: list[str] = []
    for j in (customer.get("jtbd") or [])[:1]:
        out.append(f"JTBD holds: {(j.get('statement') or '')[:100]}.")
    if (metrics.get("north_star_metric") or {}).get("name"):
        out.append("North star metric is the right success measure for this scope.")
    if feasibility.get("phases"):
        out.append("Phased delivery (MVP → V1 → V2) is feasible with current dependencies.")
    return out[:5] if out else ["Customer and segment assumptions hold.", "Technical dependencies can be met."]


def _open_questions(customer: dict, risk: dict, requirements: dict) -> list[str]:
    """Open questions before or during build."""
    out: list[str] = []
    for g in (customer.get("research_gaps") or [])[:3]:
        if isinstance(g, str):
            out.append(g)
    for w in (risk.get("warnings") or [])[:1]:
        if isinstance(w, str) and "re-run" not in w.lower():
            out.append(w[:120])
    return out[:5] if out else ["Which segment to prioritize first?", "What is the minimum viable instrumentation set?"]


def _scope_now(
    in_scope_now: list, has_high_complexity: bool, requirements: dict
) -> list[str]:
    """What to include in scope now (MVP)."""
    if in_scope_now:
        return [str(x)[:120] for x in in_scope_now[:12]]
    reqs = requirements.get("requirements") or []
    must = [r.get("title") or r.get("id", "") for r in reqs if (r.get("priority") or "").lower() == "must"]
    if must:
        return must[:10]
    return ["Core checkout flow", "Billing dashboard basics", "Payment and invoice export"][:5]


def _scope_later(
    out_of_scope: list, v1_scope: list, requirements: dict
) -> list[str]:
    """What to defer."""
    out: list[str] = []
    for x in out_of_scope[:5]:
        out.append(str(x)[:100])
    for x in v1_scope[:5]:
        out.append(str(x)[:100])
    if not out:
        out = ["Advanced analytics", "Full WCAG 2.1 AA hardening", "Multi-region data residency"]
    return out[:8]


def _success_metrics(metrics: dict) -> list[str]:
    """From north star and input metrics."""
    out: list[str] = []
    ns = metrics.get("north_star_metric") or {}
    if ns.get("name"):
        out.append(ns.get("name") or "")
    for m in (metrics.get("input_metrics") or [])[:4]:
        name = m.get("name") if isinstance(m, dict) else str(m)
        if name:
            out.append(str(name))
    for g in (metrics.get("guardrails") or [])[:2]:
        name = g.get("name") if isinstance(g, dict) else str(g)
        if name:
            out.append(f"Guardrail: {name}")
    return out[:8] if out else ["Checkout completion rate", "Payment failure rate", "Billing NPS"]


def _decision_rationale(
    gating_decision: str,
    risk_high: bool,
    has_high_complexity: bool,
    mostly_speculative: bool,
    metrics_weak: bool,
    opportunity_strong: bool,
    risk: dict,
) -> str:
    """Why this recommendation and gating."""
    parts: list[str] = []
    parts.append(f"Gating set to {gating_decision}.")
    if risk_high:
        parts.append("Risk assessment indicates material or high-severity issues; we avoid an aggressive go-forward until mitigations or validation are in place.")
    if has_high_complexity:
        parts.append("Feasibility shows high complexity in one or more areas; MVP scope was narrowed and phased delivery recommended.")
    if mostly_speculative:
        parts.append("Customer insights are mostly speculative; we recommend validating first (interviews, surveys) before committing scope.")
    if metrics_weak and opportunity_strong:
        parts.append("Metrics baselines are weak but opportunity is strong; proceed with mitigations and instrumentation plan.")
    if opportunity_strong and not risk_high:
        parts.append("Opportunity is clear and risks are manageable; recommendation supports proceeding with clear success criteria and guardrails.")
    return " ".join(parts)[:1000]
