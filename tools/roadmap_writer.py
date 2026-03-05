from __future__ import annotations
from pathlib import Path
from typing import Any, Dict

def _safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip() or default

def _risk_level_from_gating(gating: str, has_critical: bool) -> str:
    g = (gating or "").lower()
    if has_critical or g in ("do not pursue",):
        return "High"
    if g in ("validate first", "proceed with mitigations"):
        return "Medium"
    return "Low"

def write_roadmap(
    final_recommendation: Dict[str, Any],
    findings_feasibility: Dict[str, Any] | None,
    findings_risk: Dict[str, Any] | None,
    out_path: str | Path,
) -> None:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    feasibility = findings_feasibility or {}
    risk = findings_risk or {}

    bundle_id = _safe_str(final_recommendation.get("bundle_id"), "unknown")
    gating = _safe_str(final_recommendation.get("gating_decision"))
    rec_direction = _safe_str(final_recommendation.get("recommended_direction"))

    phases = feasibility.get("phases") or {}
    deps = feasibility.get("dependencies") or []
    constraints = feasibility.get("constraints") or []
    complexity = feasibility.get("complexity") or []

    deps_mvp: list[str] = []
    deps_v1: list[str] = []
    deps_v2: list[str] = []
    for d in deps:
        did = _safe_str(d.get("id"))
        phase_tags = d.get("phases") or []
        if not did:
            continue
        if "MVP" in phase_tags:
            deps_mvp.append(did)
        if "V1" in phase_tags:
            deps_v1.append(did)
        if "V2" in phase_tags:
            deps_v2.append(did)

    has_critical = any(
        (r.get("severity") or "").lower() in ("high", "critical")
        for r in (risk.get("risks") or [])
    )
    risk_level = _risk_level_from_gating(gating, has_critical)

    def phase_block(name: str) -> Dict[str, Any]:
        ph = phases.get(name) or {}
        in_scope = ph.get("in_scope") or []
        if not in_scope and name == "MVP":
            in_scope = final_recommendation.get("recommended_scope_now") or []
        if not in_scope and name in ("V1", "V2"):
            in_scope = final_recommendation.get("recommended_scope_later") or []

        if name == "MVP":
            deps_here = deps_mvp
        elif name == "V1":
            deps_here = deps_v1
        else:
            deps_here = deps_v2

        theme = f"{name} – deliver core value"
        if name == "V1":
            theme = "V1 – extend coverage and resilience"
        if name == "V2":
            theme = "V2 – optimizations and advanced capabilities"

        high_topics = [
            c.get("topic") for c in complexity if (c.get("bucket") or "").lower() == "high"
        ]
        risk_lvl = risk_level
        if high_topics and name in ("MVP", "V1") and risk_lvl == "Low":
            risk_lvl = "Medium"

        return {
            "theme": theme,
            "items": [str(x) for x in in_scope][:20],
            "dependencies": deps_here,
            "risk_level": risk_lvl,
            "notes": {
                "gating_decision": gating,
                "recommended_direction": rec_direction,
                "high_complexity_topics": high_topics,
                "constraints_summary": [c.get("description", "") for c in constraints][:5],
            },
        }

    roadmap = {
        "bundle_id": bundle_id,
        "mvp": phase_block("MVP"),
        "v1": phase_block("V1"),
        "v2": phase_block("V2"),
    }

    out.write_text(
        __import__("json").dumps(roadmap, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

