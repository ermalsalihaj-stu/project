from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, List

def _normalize_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()

def _split_sentences(text: str) -> List[str]:
    text = (text or "").replace("\n", " ").strip()
    if not text:
        return []
    parts: List[str] = []
    buf = []
    for ch in text:
        buf.append(ch)
        if ch in ".!?":
            sent = "".join(buf).strip()
            if sent:
                parts.append(sent)
            buf = []
    if buf:
        sent = "".join(buf).strip()
        if sent:
            parts.append(sent)
    return parts

def _parse_competitors(competitors_text: str, customer_notes: str) -> List[Dict[str, Any]]:
    """
    Heuristic parser for competitors.md-style free text.
    Tries to infer 2–4 competitor entries from headings/paragraphs/bullets.
    """
    text = (competitors_text or "").strip()
    if not text:
        return []

    lines = [l.rstrip() for l in text.splitlines()]
    blocks: List[List[str]] = []
    current: List[str] = []
    for line in lines:
        if not line.strip():
            if current:
                blocks.append(current)
                current = []
            continue
        if line.lstrip().startswith(("#", "##", "###")) and current:
            blocks.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        blocks.append(current)
    if len(blocks) == 1:
        big = blocks[0]
        tmp_blocks: List[List[str]] = []
        cur: List[str] = []
        for line in big:
            if any(
                kw in line.lower()
                for kw in ["competitor", "alt ", "alternative", " vs ", ":", " - "]
            ) and cur:
                tmp_blocks.append(cur)
                cur = [line]
            else:
                cur.append(line)
        if cur:
            tmp_blocks.append(cur)
        if len(tmp_blocks) > 1:
            blocks = tmp_blocks

    competitors: List[Dict[str, Any]] = []

    def add_comp(raw_lines: List[str]) -> None:
        raw = "\n".join(raw_lines).strip()
        if not raw:
            return
        first_line = raw_lines[0].lstrip("#").strip()
        name = first_line
        if ":" in name:
            name = name.split(":", 1)[0].strip()
        if "- " in name:
            name = name.split("- ", 1)[0].strip()

        lower = raw.lower()
        strengths: List[str] = []
        weaknesses: List[str] = []
        relevant_features: List[str] = []
        pricing_notes = ""
        target_segment = ""

        for ln in raw_lines:
            lstripped = ln.strip()
            llower = lstripped.lower()
            if lstripped.startswith(("- ", "* ")):
                content = lstripped[2:].strip()
                if any(k in llower for k in ["strength", "good at", "advantage"]):
                    strengths.append(content)
                elif any(k in llower for k in ["weakness", "bad at", "gap", "drawback"]):
                    weaknesses.append(content)
                elif any(k in llower for k in ["feature", "flow", "capability"]):
                    relevant_features.append(content)
                elif any(k in llower for k in ["price", "pricing", "positioning"]):
                    pricing_notes = (pricing_notes + " " + content).strip()
                else:
                    if not relevant_features:
                        relevant_features.append(content)
                    else:
                        strengths.append(content)
            else:
                if any(k in llower for k in ["sm b", "smb", "small business", "mid-market", "enterprise"]):
                    target_segment = "SMB" if "smb" in llower or "small" in llower else "Enterprise"
                if any(k in llower for k in ["price", "pricing", "position", "premium", "budget"]):
                    pricing_notes = (pricing_notes + " " + lstripped).strip()

        if not strengths and customer_notes:
            if name and name.lower() in customer_notes.lower():
                strengths.append("Recognized option among current customers.")

        competitors.append(
            {
                "name": name or "Unknown competitor",
                "strengths": strengths,
                "weaknesses": weaknesses,
                "relevant_features": relevant_features,
                "pricing_or_positioning_notes": pricing_notes,
                "target_segment": target_segment,
            }
        )

    for blk in blocks:
        add_comp(blk)

    if len(competitors) > 4:
        competitors = competitors[:4]

    return competitors

def _extract_parity_and_diff(
    competitors: List[Dict[str, Any]],
    request_summary: str,
    customer_notes: str,
) -> tuple[List[str], List[str]]:
    parity: List[str] = []
    diff: List[str] = []

    all_strengths = " ".join(
        " ".join(c.get("strengths") or []) for c in competitors
    ).lower()
    all_features = " ".join(
        " ".join(c.get("relevant_features") or []) for c in competitors
    ).lower()
    combined = " ".join(
        [request_summary.lower(), customer_notes.lower(), all_strengths, all_features]
    )

    def add_unique(lst: List[str], item: str) -> None:
        if item not in lst:
            lst.append(item)

    if any(k in combined for k in ["checkout", "payment", "billing"]):
        add_unique(parity, "Provide a clear, trustworthy checkout and billing experience.")
        add_unique(diff, "Recover from failed payments quickly with clear next steps and guidance.")

    if any(k in combined for k in ["pricing", "price", "plan"]):
        add_unique(parity, "Offer transparent pricing and plan comparison.")
        add_unique(diff, "Explain pricing in plain language with examples tailored to the target segment.")

    if any(k in combined for k in ["invoice", "export", "report"]):
        add_unique(parity, "Support exporting billing history or invoices in common formats.")
        add_unique(diff, "Make invoice export and reporting self-serve and easy to discover.")

    if any(k in combined for k in ["accessibility", "a11y", "screen reader"]):
        add_unique(parity, "Meet baseline accessibility for forms and key flows.")
        add_unique(diff, "Position accessibility as a first-class strength and document it clearly.")

    if any(k in combined for k in ["trust", "secure", "security", "gdpr", "compliance"]):
        add_unique(parity, "Communicate basic trust, security, and compliance posture.")
        add_unique(diff, "Lead with trust and safety as a core brand pillar with concrete proof points.")

    if not parity:
        parity = [
            "Meet common UX expectations for modern SaaS products (navigation, loading states, and error handling).",
            "Provide clear confirmations for primary user actions.",
        ]
    if not diff:
        diff = [
            "Differentiate on clarity and transparency in copy, not just features.",
            "Emphasize speed, reliability, and recovery from errors as core advantages.",
        ]

    return parity, diff

def _build_positioning(
    request_summary: str,
    customer_notes: str,
    parity: List[str],
    diff: List[str],
) -> str:
    summary = request_summary or customer_notes
    audience_hint = "teams" if "team" in (summary or "").lower() else "users"

    core_diff = diff[0] if diff else "a clearer and more reliable experience than alternatives"
    return (
        f"For {audience_hint} who need a dependable and understandable solution, "
        f"position the product around {core_diff.lower()}."
    )


def _build_messaging_pillars(
    parity: List[str],
    diff: List[str],
) -> List[str]:
    pillars: List[str] = []

    for item in diff[:3]:
        pillars.append(item)

    generic = [
        "Transparent billing and usage communication",
        "Fast, low-friction core flows",
        "Accessible and inclusive by default",
    ]
    for g in generic:
        if len(pillars) >= 5:
            break
        if g not in pillars:
            pillars.append(g)

    while len(pillars) < 3 and parity:
        candidate = parity.pop(0)
        if candidate not in pillars:
            pillars.append(candidate)

    return pillars[:5]

def run(context_packet: dict) -> dict:
    bundle_id = _normalize_text(context_packet.get("bundle_id"))
    request_summary = _normalize_text(context_packet.get("request_summary"))
    customer_notes = _normalize_text(context_packet.get("customer_notes_summary"))
    competitors_text = _normalize_text(context_packet.get("competitors_summary"))

    competitors = _parse_competitors(competitors_text, customer_notes)
    parity, diff = _extract_parity_and_diff(competitors, request_summary, customer_notes)
    recommended_positioning = _build_positioning(request_summary, customer_notes, parity, diff)
    messaging_pillars = _build_messaging_pillars(parity, diff)

    research_gaps: List[str] = []
    warnings: List[str] = []

    if not competitors_text:
        research_gaps.append("Competitor pack (competitors.md) is missing or empty.")
        warnings.append("Competitive analysis based mostly on request summary and notes; competitor details are sparse.")
    elif len(competitors_text) < 200 or len(competitors) < 2:
        research_gaps.append("Competitor information is shallow; no detailed strengths/weaknesses comparison available.")
        research_gaps.append("No clear pricing comparison across competitors.")
        warnings.append("Consider collecting a richer competitor pack (screenshots, pricing pages, flows).")

    if not customer_notes:
        research_gaps.append("Limited evidence about how customers talk about competitors in their own words.")

    if not request_summary:
        research_gaps.append("Product request summary is thin; positioning is more generic.")

    return {
        "bundle_id": bundle_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "competitors": competitors,
        "parity_opportunities": parity,
        "differentiation_opportunities": diff,
        "recommended_positioning": recommended_positioning,
        "messaging_pillars": messaging_pillars,
        "research_gaps": research_gaps,
        "warnings": warnings,
    }

