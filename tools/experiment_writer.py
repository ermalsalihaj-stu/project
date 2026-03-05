from __future__ import annotations
from pathlib import Path
from typing import Any, Dict

def _safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip() or default

def write_experiment_plan(
    final_recommendation: Dict[str, Any],
    findings_customer: Dict[str, Any] | None,
    findings_metrics: Dict[str, Any] | None,
    findings_risk: Dict[str, Any] | None,
    out_path: str | Path,
) -> None:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    customer = findings_customer or {}
    metrics = findings_metrics or {}
    risk = findings_risk or {}

    bundle_id = _safe_str(final_recommendation.get("bundle_id"), "unknown")
    gating = _safe_str(final_recommendation.get("gating_decision"), "Validate first")
    direction = _safe_str(final_recommendation.get("recommended_direction"))
    success_metrics = final_recommendation.get("success_metrics") or []

    segments = customer.get("segments") or []
    insights = customer.get("insights") or []
    validation_plan = customer.get("validation_plan") or []

    north_star = metrics.get("north_star_metric") or {}
    input_metrics = metrics.get("input_metrics") or []
    guardrails = metrics.get("guardrails") or []

    risks = risk.get("risks") or []

    lines: list[str] = []

    lines.append(f"# Experiment plan – {bundle_id}")
    lines.append("")

    lines.append("## Main hypotheses")
    if insights:
        for i in insights[:3]:
            stmt = _safe_str(i.get("statement"))
            conf = _safe_str(i.get("confidence"))
            if stmt:
                lines.append(f"- **[{conf}]** {stmt}")
    else:
        lines.append(
            "- Users who see the improved experience will complete the primary flow more often and with fewer support tickets."
        )
    lines.append("")

    lines.append("## What we are validating")
    if direction:
        lines.append(direction)
    else:
        lines.append(
            "We are validating that the proposed scope delivers user and business value, and that risks can be mitigated."
        )
    lines.append("")

    lines.append("## Metrics to be measured")
    if north_star.get("name"):
        lines.append(f"- **North star:** {north_star.get('name')} – {_safe_str(north_star.get('description'))}")
    if input_metrics:
        lines.append("- **Input metrics:**")
        for m in input_metrics[:4]:
            name = _safe_str(m.get("name"))
            desc = _safe_str(m.get("description"))
            lines.append(f"  - {name}: {desc}")
    if guardrails:
        lines.append("- **Guardrails:**")
        for g in guardrails[:3]:
            name = _safe_str(g.get("name"))
            desc = _safe_str(g.get("description"))
            lines.append(f"  - {name}: {desc}")
    if not (north_star or input_metrics or guardrails):
        for m in success_metrics[:3]:
            lines.append(f"- {m}")
    lines.append("")

    lines.append("## Sample size / target segment (directional)")
    if segments:
        names = ", ".join(_safe_str(s.get("name")) for s in segments[:3])
        lines.append(
            f"- Target segments: {names}. Start with a smaller subset if risk is high, then expand."
        )
    else:
        lines.append("- Target segments: primary users of the affected flow.")
    if validation_plan:
        lines.append("")
        lines.append("Planned validation activities:")
        for step in validation_plan:
            step_no = step.get("step")
            method = _safe_str(step.get("method"))
            goal = _safe_str(step.get("goal"))
            lines.append(f"- Step {step_no}: {method} – {goal}")
    lines.append("")

    lines.append("## Expected outcomes")
    if success_metrics:
        lines.append("If successful, we expect to move:")
        for m in success_metrics[:5]:
            lines.append(f"- {m}")
    else:
        lines.append(
            "- Improved completion rate for the primary flow.\n- Reduced error and drop-off at key steps."
        )
    lines.append("")

    lines.append("## Fail / pass signals")
    lines.append(f"- **Current gating decision:** {gating}")
    if risks:
        lines.append("- **Risks to watch:**")
        for r_item in risks[:5]:
            desc = _safe_str(r_item.get("description") or r_item.get("source_risk"))
            sev = _safe_str(r_item.get("severity"), "medium")
            lines.append(f"  - ({sev}) {desc}")
    lines.append("")
    lines.append(
        "- **Pass:** leading metrics move in the expected direction without breaching guardrails; we can confidently proceed to wider rollout."
    )
    lines.append(
        "- **Fail:** core success metrics do not improve, or we hit risk/guardrail thresholds that make rollout unsafe."
    )

    out.write_text("\n".join(lines), encoding="utf-8")

