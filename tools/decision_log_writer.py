from __future__ import annotations
from pathlib import Path
from typing import Any, Dict

def _safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip() or default

def write_decision_log(
    final_recommendation: Dict[str, Any],
    findings_risk: Dict[str, Any] | None,
    findings_feasibility: Dict[str, Any] | None,
    findings_competition: Dict[str, Any] | None,
    out_path: str | Path,
) -> None:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    risk = findings_risk or {}
    feasibility = findings_feasibility or {}
    competition = findings_competition or {}

    bundle_id = _safe_str(final_recommendation.get("bundle_id"), "unknown")
    gating = _safe_str(final_recommendation.get("gating_decision"), "Validate first")
    direction = _safe_str(final_recommendation.get("recommended_direction"))
    rationale = _safe_str(final_recommendation.get("decision_rationale"))

    top_risks = final_recommendation.get("top_risks") or []
    tradeoffs = final_recommendation.get("tradeoffs") or []
    open_questions = final_recommendation.get("open_questions") or []

    risk_items = risk.get("risks") or []
    mitigations = risk.get("required_mitigations") or []

    complexity = feasibility.get("complexity") or []
    phases = feasibility.get("phases") or {}

    competitors = competition.get("competitors") or []
    parity = competition.get("parity_opportunities") or []
    diff = competition.get("differentiation_opportunities") or []

    lines: list[str] = []

    lines.append(f"# Decision log – {bundle_id}")
    lines.append("")

    lines.append("## Final decision")
    lines.append(f"- **Gating decision:** {gating}")
    if direction:
        lines.append(f"- **Direction:** {direction}")
    lines.append("")

    lines.append("## Alternatives considered")
    if tradeoffs:
        for t in tradeoffs[:6]:
            lines.append(f"- {t}")
    else:
        lines.append(
            "- Proceed vs. validate-first with narrower MVP; final choice documented above."
        )
    if competitors:
        lines.append("")
        lines.append("Competitive context:")
        names = ", ".join(_safe_str(c.get("name")) for c in competitors[:4])
        lines.append(f"- Key competitors: {names}")
        if parity:
            lines.append(f"- Parity must-haves: {', '.join(parity[:3])}")
        if diff:
            lines.append(f"- Differentiation angles: {', '.join(diff[:3])}")
    lines.append("")

    lines.append("## Why other alternatives were rejected")
    if rationale:
        lines.append(rationale)
    else:
        lines.append(
            "Other options were rejected due to a combination of risk profile, complexity, and limited validation."
        )
    lines.append("")

    lines.append("## Risks accepted")
    if risk_items:
        for r_item in risk_items[:10]:
            desc = _safe_str(r_item.get("description") or r_item.get("source_risk"))
            sev = _safe_str(r_item.get("severity"), "medium")
            lines.append(f"- ({sev}) {desc}")
    elif top_risks:
        for tr in top_risks[:5]:
            lines.append(f"- {tr}")
    else:
        lines.append("- No explicit risks captured; treat this as a documentation gap.")
    lines.append("")

    lines.append("## Mitigations required")
    if mitigations:
        for m in mitigations:
            lines.append(f"- {m}")
    else:
        lines.append("- Mitigations to be defined based on risk output.")
    lines.append("")

    lines.append("## Delivery and complexity notes")
    high_complexity = [
        c.get("topic") for c in complexity if (c.get("bucket") or "").lower() == "high"
    ]
    if high_complexity:
        lines.append(
            f"- High-complexity areas: {', '.join(str(t) for t in high_complexity[:5])}"
        )
    if phases:
        mvp = phases.get("MVP") or {}
        v1 = phases.get("V1") or {}
        lines.append(
            f"- MVP focus: {', '.join(str(x) for x in (mvp.get('in_scope') or [])[:5])}"
        )
        lines.append(
            f"- V1+ later: {', '.join(str(x) for x in (v1.get('in_scope') or [])[:5])}"
        )
    lines.append("")

    lines.append("## Open questions")
    if open_questions:
        for q in open_questions[:10]:
            lines.append(f"- {q}")
    else:
        lines.append("- What further validation is required before full rollout?")

    out.write_text("\n".join(lines), encoding="utf-8")

