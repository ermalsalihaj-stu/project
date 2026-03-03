"""
Metrics & Analytics Agent (Agent D).

Consumes context_packet from Intake Agent; produces North Star, input metrics,
guardrails, event taxonomy, and metric integrity issues + recommendations.
Output: findings_metrics.json (schema: findings_metrics.schema.json).
"""
from __future__ import annotations

from typing import Any


def run(context_packet: dict) -> dict:
    """
    Run the Metrics & Analytics agent.
    Input: context_packet (from Intake agent).
    Returns: dict conforming to findings_metrics.schema.json.
    """
    bundle_id = context_packet.get("bundle_id", "unknown")
    request_summary = (context_packet.get("request_summary") or "").strip()
    tickets = context_packet.get("tickets") or []
    customer_notes = (context_packet.get("customer_notes_summary") or "").strip()
    metrics_snapshot = context_packet.get("metrics_snapshot") or {}

    # 1) Feature area + goals
    feature_area = _derive_feature_area(request_summary, tickets, customer_notes)
    goals = _derive_goals(request_summary, tickets, customer_notes)

    # 2) North Star, input metrics, guardrails (from snapshot when present, else defaults)
    north_star_metric = _derive_north_star(metrics_snapshot, request_summary)
    input_metrics = _derive_input_metrics(metrics_snapshot, request_summary)
    guardrails = _derive_guardrails(metrics_snapshot, request_summary)

    # 3) Event taxonomy (6–10 events)
    event_taxonomy = _build_event_taxonomy(feature_area, tickets, request_summary)

    # 4) Metric integrity: issues + recommendations
    issues = _check_metric_integrity(metrics_snapshot, event_taxonomy)
    recommendations = _build_recommendations(issues, metrics_snapshot)

    return {
        "bundle_id": bundle_id,
        "feature_area": feature_area,
        "goals": goals,
        "north_star_metric": north_star_metric,
        "input_metrics": input_metrics,
        "guardrails": guardrails,
        "event_taxonomy": event_taxonomy,
        "issues": issues,
        "recommendations": recommendations,
    }


def _derive_feature_area(request_summary: str, tickets: list, customer_notes: str) -> str:
    """Single feature area string from request, tickets, notes."""
    text = f"{request_summary} {customer_notes}".lower()
    ticket_titles = " ".join([str(t.get("title") or "") for t in tickets]).lower()

    # Simple keyword extraction
    if any(k in text or k in ticket_titles for k in ["checkout", "billing", "payment"]):
        return "Checkout & Billing"
    if any(k in text or k in ticket_titles for k in ["onboarding", "activation"]):
        return "Onboarding & Activation"
    if any(k in text or k in ticket_titles for k in ["retention", "churn"]):
        return "Retention & Engagement"
    if any(k in text or k in ticket_titles for k in ["dashboard", "analytics"]):
        return "Product Analytics & Dashboard"

    # Fallback: first meaningful phrase from request
    first_line = (request_summary or "").split(".")[0].strip()[:80]
    return first_line or "Product scope"


def _derive_goals(request_summary: str, tickets: list, customer_notes: str) -> list[str]:
    """2–3 short goals."""
    goals: list[str] = []
    text = (request_summary or "").lower()
    if "checkout" in text or "billing" in text:
        goals.append("Reduce checkout drop-off and clarify pricing")
        goals.append("Improve billing dashboard and enterprise compliance (SSO, GDPR)")
    if "friction" in text or "confusion" in text or "streamline" in text:
        goals.append("Streamline user flows and reduce friction")
    if not goals:
        goals.append("Improve core product metrics and user satisfaction")
        goals.append("Establish baseline metrics and guardrails")
    return goals[:2] if len(goals) == 2 else goals[:3]


def _derive_north_star(metrics_snapshot: dict, request_summary: str) -> dict[str, str]:
    """One North Star metric."""
    candidate = (metrics_snapshot or {}).get("north_star_candidate")
    if candidate and isinstance(candidate, str):
        return {"name": candidate, "description": candidate, "unit": "rate or count"}
    # Default from domain
    if "checkout" in (request_summary or "").lower():
        return {
            "name": "Weekly successful checkouts",
            "description": "Count of completed checkouts (payment confirmed) per week",
            "unit": "count/week",
        }
    return {
        "name": "Activation rate",
        "description": "Share of new users completing key success action within first 7 days",
        "unit": "rate",
    }


def _derive_input_metrics(metrics_snapshot: dict, request_summary: str) -> list[dict[str, str]]:
    """3–6 metrics that drive North Star."""
    out: list[dict[str, str]] = []
    funnel = (metrics_snapshot or {}).get("funnel") or {}
    product_health = (metrics_snapshot or {}).get("product_health") or {}

    for key in list(funnel.keys())[:4]:
        label = key.replace("_", " ").title()
        out.append({"name": key, "description": f"Funnel step: {label}", "unit": "rate"})
    for key in list(product_health.keys())[:2]:
        label = key.replace("_", " ").title()
        out.append({"name": key, "description": f"Product health: {label}", "unit": "rate or count"})

    defaults = [
        {"name": "cart_to_checkout_start", "description": "Share of cart viewers who start checkout", "unit": "rate"},
        {"name": "checkout_start_to_payment", "description": "Share of checkout starts reaching payment", "unit": "rate"},
        {"name": "payment_to_confirmation", "description": "Share of payments that confirm successfully", "unit": "rate"},
        {"name": "checkout_abandonment_rate", "description": "Share of started checkouts abandoned", "unit": "rate"},
    ]
    for d in defaults:
        if len(out) >= 6:
            break
        if not any(m["name"] == d["name"] for m in out):
            out.append(d)
    return out[:6]


def _derive_guardrails(metrics_snapshot: dict, request_summary: str) -> list[dict[str, str]]:
    """3–5 metrics that must not degrade."""
    out: list[dict[str, str]] = []
    guards = (metrics_snapshot or {}).get("guardrails") or {}
    for key in list(guards.keys())[:5]:
        label = key.replace("_", " ").title()
        out.append({"name": key, "description": f"Guardrail: {label}", "unit": "rate or score"})

    defaults = [
        {"name": "payment_failure_rate", "description": "Share of payment attempts that fail", "unit": "rate"},
        {"name": "billing_nps", "description": "NPS or satisfaction score for billing", "unit": "score"},
        {"name": "error_rate", "description": "Server/client error rate", "unit": "rate"},
        {"name": "refund_rate", "description": "Share of transactions refunded", "unit": "rate"},
        {"name": "p95_latency", "description": "95th percentile latency for critical paths", "unit": "ms"},
    ]
    for d in defaults:
        if len(out) >= 5:
            break
        if not any(m["name"] == d["name"] for m in out):
            out.append(d)
    return out[:5]


def _build_event_taxonomy(feature_area: str, tickets: list, request_summary: str) -> list[dict[str, Any]]:
    """6–10 events with event_name, description, trigger, properties, required_properties, user_properties, notes."""
    area_lower = feature_area.lower()
    events: list[dict[str, Any]] = []

    # Checkout/billing events
    if "checkout" in area_lower or "billing" in (request_summary or "").lower():
        events.extend([
            {
                "event_name": "cart_viewed",
                "description": "User viewed cart page",
                "trigger": "Page view or cart component mount",
                "properties": ["cart_id", "item_count", "total_value"],
                "required_properties": ["cart_id"],
                "user_properties": ["segment", "is_returning"],
                "notes": "Log in cart service or frontend; include segment from user context.",
            },
            {
                "event_name": "checkout_started",
                "description": "User started checkout flow",
                "trigger": "First checkout step submitted",
                "properties": ["checkout_id", "step_id", "cart_id"],
                "required_properties": ["checkout_id", "step_id"],
                "user_properties": ["segment", "is_returning"],
                "notes": "Emit at entry to checkout funnel; backend or frontend.",
            },
            {
                "event_name": "checkout_step_completed",
                "description": "User completed a checkout step",
                "trigger": "Step validation passed and user advanced",
                "properties": ["checkout_id", "step_id", "duration_seconds"],
                "required_properties": ["checkout_id", "step_id"],
                "user_properties": ["segment"],
                "notes": "Include step_id and drop_off_reason when step is abandoned (instrumentation_gaps).",
            },
            {
                "event_name": "payment_started",
                "description": "User initiated payment",
                "trigger": "Payment method selected and submit clicked",
                "properties": ["checkout_id", "payment_method_type", "amount"],
                "required_properties": ["checkout_id", "payment_method_type"],
                "user_properties": ["segment"],
                "notes": "Log before PSP call; tag segment for billing events.",
            },
            {
                "event_name": "payment_completed",
                "description": "Payment confirmed successfully",
                "trigger": "PSP callback or confirmation",
                "properties": ["checkout_id", "transaction_id", "amount", "currency"],
                "required_properties": ["checkout_id", "transaction_id"],
                "user_properties": ["segment"],
                "notes": "Backend; use for North Star (successful checkouts).",
            },
            {
                "event_name": "payment_failed",
                "description": "Payment attempt failed",
                "trigger": "PSP returned error or timeout",
                "properties": ["checkout_id", "error_code", "payment_method_type"],
                "required_properties": ["checkout_id", "error_code"],
                "user_properties": ["segment"],
                "notes": "Backend; feed guardrail payment_failure_rate.",
            },
            {
                "event_name": "checkout_abandoned",
                "description": "User left checkout without completing",
                "trigger": "Session exit or timeout on checkout",
                "properties": ["checkout_id", "last_step_id", "drop_off_reason"],
                "required_properties": ["checkout_id", "last_step_id"],
                "user_properties": ["segment"],
                "notes": "Frontend or backend timeout; include drop_off_reason when available.",
            },
            {
                "event_name": "billing_dashboard_viewed",
                "description": "User viewed billing or subscription dashboard",
                "trigger": "Page view",
                "properties": ["page", "subscription_id"],
                "required_properties": ["page"],
                "user_properties": ["segment", "plan"],
                "notes": "Tag segment for segmentation; use for billing NPS context.",
            },
        ])

    # Generic product events if we have few
    if len(events) < 6:
        events.extend([
            {
                "event_name": "feature_used",
                "description": "User used a key product feature",
                "trigger": "Feature interaction",
                "properties": ["feature_id", "action"],
                "required_properties": ["feature_id"],
                "user_properties": ["segment", "is_new_user"],
                "notes": "Instrument in app; segment for new vs returning.",
            },
            {
                "event_name": "form_validation_error",
                "description": "Form validation failed (e.g. checkout or signup)",
                "trigger": "Validation failed on submit or blur",
                "properties": ["form_id", "field", "error_type", "a11y_context"],
                "required_properties": ["form_id", "field"],
                "user_properties": ["segment"],
                "notes": "Include a11y context for WCAG-related friction (instrumentation_gaps).",
            },
        ])

    return events[:10] if len(events) > 10 else events


def _check_metric_integrity(metrics_snapshot: dict, event_taxonomy: list) -> list[dict[str, str]]:
    """missing_baselines, missing_segmentation, tracking_gaps."""
    issues: list[dict[str, str]] = []

    if not metrics_snapshot or not isinstance(metrics_snapshot, dict):
        issues.append({
            "type": "missing_baselines",
            "description": "No metrics_snapshot in context; baseline values and time_window are missing.",
        })
    else:
        has_funnel = bool(metrics_snapshot.get("funnel"))
        has_guardrails = bool(metrics_snapshot.get("guardrails"))
        if not has_funnel and not has_guardrails:
            issues.append({
                "type": "missing_baselines",
                "description": "metrics_snapshot has no funnel or guardrails; baselines missing.",
            })
        if not metrics_snapshot.get("segments"):
            issues.append({
                "type": "missing_segmentation",
                "description": "No segment-level breakdown (e.g. new vs returning, SMB vs Enterprise) in metrics_snapshot.",
            })
        gaps = metrics_snapshot.get("instrumentation_gaps") or []
        if gaps:
            for g in gaps[:5]:
                issues.append({
                    "type": "tracking_gaps",
                    "description": g if isinstance(g, str) else str(g),
                })

    # Ensure we have at least one issue type if snapshot was empty
    if not issues and (not metrics_snapshot or not metrics_snapshot.get("time_window")):
        issues.append({
            "type": "missing_baselines",
            "description": "time_window missing in metrics_snapshot; cannot compare periods.",
        })

    return issues


def _build_recommendations(issues: list[dict], metrics_snapshot: dict) -> list[str]:
    """Recommendations to address issues."""
    recs: list[str] = []
    types = {i.get("type") for i in issues}

    if "missing_baselines" in types:
        recs.append("Add metrics_snapshot with time_window, funnel (with baseline/current/trend), and guardrails.")
    if "missing_segmentation" in types:
        recs.append("Add segments (e.g. SMB, Enterprise, new vs returning) to metrics_snapshot for breakdowns.")
    if "tracking_gaps" in types:
        recs.append("Implement missing events and properties from event_taxonomy; add segment and a11y context where noted.")
    if not recs:
        recs.append("Keep metrics_snapshot and event instrumentation in sync with product changes.")
    return recs
