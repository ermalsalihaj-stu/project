"""
Customer Insights Agent (Agent B).

Consumes context_packet from Intake Agent; produces segments, JTBD, insights
(Validated/Directional/Speculative), research gaps, and a minimal validation plan.
Output: findings_customer.json (schema: findings_customer.schema.json).
"""
from __future__ import annotations

from typing import Any


def run(context_packet: dict) -> dict:
    """
    Run the Customer Insights agent.
    Input: context_packet (from Intake agent).
    Returns: dict conforming to findings_customer.schema.json.
    """
    bundle_id = context_packet.get("bundle_id", "unknown")
    request_summary = (context_packet.get("request_summary") or "").strip()
    tickets = context_packet.get("tickets") or []
    customer_notes = (context_packet.get("customer_notes_summary") or "").strip()

    segments = _extract_segments(tickets, customer_notes, request_summary)
    jtbd = _derive_jtbd(request_summary, tickets, customer_notes)
    insights = _build_insights(tickets, customer_notes, request_summary, segments)
    research_gaps = _derive_research_gaps(tickets, customer_notes, request_summary)
    validation_plan = _build_validation_plan(research_gaps)

    return {
        "bundle_id": bundle_id,
        "segments": segments,
        "jtbd": jtbd,
        "insights": insights,
        "research_gaps": research_gaps,
        "validation_plan": validation_plan,
    }


def _extract_segments(
    tickets: list, customer_notes: str, request_summary: str
) -> list[dict[str, str]]:
    """Extract segments from tickets (segment field) and notes; ensure at least 2."""
    seen: set[str] = set()
    segments_list: list[dict[str, str]] = []

    # From tickets
    for t in tickets:
        seg = t.get("segment") or (t.get("_raw") or {}).get("segment")
        if seg and isinstance(seg, str) and seg.strip():
            seg_id = seg.lower().replace(" ", "_").strip()
            if seg_id not in seen:
                seen.add(seg_id)
                segments_list.append({
                    "id": seg_id,
                    "name": seg.strip(),
                    "description": _segment_description(seg, tickets),
                })

    # Infer from notes/request if we have fewer than 2
    text = f"{customer_notes} {request_summary}".lower()
    defaults = [
        ("smb", "SMB", "Small and medium businesses; self-serve, price-sensitive, need clarity on pricing and quick checkout."),
        ("enterprise", "Enterprise", "Enterprise customers; need SSO, GDPR-compliant billing, procurement workflows, and per-seat clarity."),
        ("all", "All", "Cross-segment; issues affecting all users (e.g. auth, accessibility)."),
        ("new_users", "New users", "First-time or trial users; need streamlined onboarding and checkout."),
        ("returning", "Returning users", "Existing customers; expect saved payment, one-click checkout, billing dashboard."),
    ]
    for seg_id, name, desc in defaults:
        if seg_id not in seen and (seg_id in text or name.lower() in text or len(segments_list) < 2):
            seen.add(seg_id)
            segments_list.append({"id": seg_id, "name": name, "description": desc})
        if len(segments_list) >= 2:
            break

    # Ensure at least 2
    while len(segments_list) < 2 and defaults:
        for seg_id, name, desc in defaults:
            if seg_id not in seen:
                seen.add(seg_id)
                segments_list.append({"id": seg_id, "name": name, "description": desc})
                break
        else:
            break

    return segments_list[:8]


def _segment_description(segment_name: str, tickets: list) -> str:
    """One-line description for segment from ticket context."""
    seg_lower = segment_name.lower()
    if "smb" in seg_lower or "small" in seg_lower:
        return "SMB segment; focus on self-serve, pricing clarity, and checkout simplicity."
    if "enterprise" in seg_lower:
        return "Enterprise segment; focus on compliance, SSO, procurement, and billing controls."
    if seg_lower == "all":
        return "All segments; cross-cutting issues (e.g. auth, a11y)."
    count = sum(1 for t in tickets if (t.get("segment") or "").lower() == seg_lower or ((t.get("_raw") or {}).get("segment") or "").lower() == seg_lower)
    return f"Segment: {segment_name}; referenced in {count} ticket(s)."


def _derive_jtbd(
    request_summary: str, tickets: list, customer_notes: str
) -> list[dict[str, Any]]:
    """Jobs To Be Done – at least 1."""
    jtbd_list: list[dict[str, Any]] = []
    text = f"{request_summary} {customer_notes}".lower()
    ticket_titles = [str(t.get("title") or "") for t in tickets]

    if "checkout" in text or any("checkout" in t.lower() for t in ticket_titles):
        jtbd_list.append({
            "id": "jtbd_checkout",
            "statement": "When I buy or subscribe, I want to complete payment quickly and with minimal steps so that I don't abandon or get confused.",
            "context": "Checkout and payment flow; drop-off and friction reported.",
            "related_segments": ["SMB", "Enterprise", "All"],
        })
    if "billing" in text or "pricing" in text or any("billing" in t.lower() or "pricing" in t.lower() for t in ticket_titles):
        jtbd_list.append({
            "id": "jtbd_billing",
            "statement": "When I manage my subscription or invoices, I want to see clear pricing and exportable records so that I can reconcile and comply with my organization.",
            "context": "Billing dashboard, pricing display, invoice export, GDPR.",
            "related_segments": ["SMB", "Enterprise"],
        })
    if "auth" in text or "login" in text or any("login" in t.lower() or "auth" in t.lower() for t in ticket_titles):
        jtbd_list.append({
            "id": "jtbd_auth",
            "statement": "When I update my payment or billing info, I want my session to stay valid so that I don't lose progress or see cryptic errors.",
            "context": "Auth and session during billing updates.",
            "related_segments": ["All"],
        })

    if not jtbd_list:
        jtbd_list.append({
            "id": "jtbd_core",
            "statement": "When I use the product, I want key flows to be clear and reliable so that I can achieve my goal without friction or confusion.",
            "context": "Derived from request and tickets.",
            "related_segments": ["All"],
        })

    return jtbd_list


def _build_insights(
    tickets: list, customer_notes: str, request_summary: str, segments: list[dict]
) -> list[dict[str, Any]]:
    """5–10 insights with id, statement, evidence_refs, confidence (Validated/Directional/Speculative), impacted_segments."""
    insights_list: list[dict[str, Any]] = []
    segment_names = [s["name"] for s in segments]

    # Map ticket id for evidence_refs
    def tid(t: dict) -> str:
        return str(t.get("id") or t.get("key") or "")

    # From tickets -> insights (mix of Validated / Directional / Speculative)
    for i, t in enumerate(tickets[:12]):
        title = str(t.get("title") or "")
        desc = str(t.get("description") or "")
        seg = t.get("segment") or (t.get("_raw") or {}).get("segment") or "All"
        if not seg or seg not in segment_names:
            seg = "All" if "All" in segment_names else (segment_names[0] if segment_names else "All")
        impacted = [seg] if seg != "All" else segment_names[:3] or ["All"]

        # Confidence: Support/Sales/QA -> more Validated; Product/Backlog -> Directional; else Speculative
        source = (t.get("source") or (t.get("_raw") or {}).get("source") or "").lower()
        if source in ("support", "sales", "qa"):
            confidence = "Validated"
        elif source in ("product",) and t.get("priority") == "High":
            confidence = "Directional"
        else:
            confidence = "Speculative"

        statement = title
        if len(desc) > 20:
            statement = f"{title}: {desc[:120].strip()}..." if len(desc) > 120 else f"{title}: {desc.strip()}"

        insights_list.append({
            "id": f"insight_{i+1}",
            "statement": statement[:400],
            "evidence_refs": [tid(t)] if tid(t) else [],
            "confidence": confidence,
            "impacted_segments": impacted,
        })

    # Add a few from customer_notes/request if we have room
    if len(insights_list) < 10 and customer_notes:
        snippet = customer_notes[:200].strip()
        insights_list.append({
            "id": "insight_notes_1",
            "statement": f"Customer notes indicate: {snippet}...",
            "evidence_refs": ["customer_notes"],
            "confidence": "Directional",
            "impacted_segments": segment_names[:2] or ["All"],
        })
    if len(insights_list) < 10 and request_summary:
        insights_list.append({
            "id": "insight_request_1",
            "statement": f"Request summary: {request_summary[:300].strip()}...",
            "evidence_refs": ["request_summary"],
            "confidence": "Directional",
            "impacted_segments": segment_names[:2] or ["All"],
        })

    # Ensure 5–10 insights
    if len(insights_list) < 5:
        insights_list = (insights_list + _default_insights(segment_names))[:10]
    return insights_list[:10]


def _default_insights(segment_names: list[str]) -> list[dict[str, Any]]:
    """Fallback insights to reach at least 5."""
    seg = segment_names[:2] or ["All"]
    return [
        {"id": "insight_d1", "statement": "Checkout drop-off is a top concern; need funnel and step-level instrumentation.", "evidence_refs": [], "confidence": "Directional", "impacted_segments": seg},
        {"id": "insight_d2", "statement": "Pricing clarity and billing transparency are requested across segments.", "evidence_refs": [], "confidence": "Directional", "impacted_segments": seg},
        {"id": "insight_d3", "statement": "Enterprise needs GDPR-compliant export and data residency options.", "evidence_refs": [], "confidence": "Speculative", "impacted_segments": seg},
    ]


def _derive_research_gaps(tickets: list, customer_notes: str, request_summary: str) -> list[str]:
    """3–5 research gaps: what we don't know yet."""
    gaps = [
        "Exact drop-off reasons at each checkout step (quantitative + qualitative).",
        "Segment-level preference for guest checkout vs account (SMB vs Enterprise).",
        "Which pricing display format (breakdown, tooltips, comparison) best reduces support tickets.",
    ]
    if "enterprise" in f"{customer_notes} {request_summary}".lower():
        gaps.append("Enterprise procurement cycle and approval workflows for billing changes.")
    if any("a11y" in str(t.get("title") or "").lower() or "wcag" in str(t.get("description") or "").lower() for t in tickets):
        gaps.append("Accessibility friction points and screen-reader usage in checkout.")
    return gaps[:5]


def _build_validation_plan(research_gaps: list[str]) -> list[dict[str, Any]]:
    """3–5 minimal validation steps: survey, interviews, log analysis, A/B smoke."""
    return [
        {"step": 1, "method": "5 user interviews", "goal": "Validate top drop-off reasons and pricing confusion."},
        {"step": 2, "method": "Survey (N≥50)", "goal": "Segment preferences (guest checkout, billing dashboard)."},
        {"step": 3, "method": "Log analysis", "goal": "Funnel step completion and error rates by segment."},
        {"step": 4, "method": "A/B smoke test", "goal": "Pricing display variant vs support ticket volume."},
        {"step": 5, "method": "Accessibility audit", "goal": "WCAG 2.1 AA and friction events (if a11y in scope)."},
    ][:5]
