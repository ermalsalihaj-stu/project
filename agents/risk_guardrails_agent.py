from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml


@dataclass
class RuleResult:
    rule_id: str
    decision: str
    matched_risk: str
    evidence_count: int
    missing_mitigation_keys: List[str]
    required_mitigations: List[str]


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _load_policy() -> Dict[str, Any]:
    policy_path = _project_root() / "policies" / "guardrails.yaml"
    if not policy_path.exists():
        raise FileNotFoundError(f"guardrails policy not found: {policy_path}")
    return yaml.safe_load(policy_path.read_text(encoding="utf-8")) or {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text_corpus(findings_requirements: Optional[Dict[str, Any]]) -> str:
    if not findings_requirements:
        return ""

    parts: List[str] = []

    # requirements
    for r in findings_requirements.get("requirements", []) or []:
        parts.append(str(r.get("title", "")))
        parts.append(str(r.get("statement", "")))
        for ac in (r.get("acceptance_criteria", []) or []):
            parts.append(str(ac))

    # edge_cases
    for e in findings_requirements.get("edge_cases", []) or []:
        parts.append(str(e.get("description", "")))

    # backlog (epics + stories)
    backlog = findings_requirements.get("backlog") or {}
    for e in backlog.get("epics", []) or []:
        parts.append(str(e.get("title", "")))
        parts.append(str(e.get("description", "")))
    for s in backlog.get("stories", []) or []:
        parts.append(str(s.get("title", "")))
        parts.append(str(s.get("description", "")))
        for ac in (s.get("acceptance_criteria", []) or []):
            parts.append(str(ac))

    return " ".join(p for p in parts if p).lower()


def _count_evidence(context_packet: Dict[str, Any], risk_key: str) -> Tuple[int, List[str]]:
    # ticket-level evidence from risk_hotspots
    hotspots = context_packet.get("risk_hotspots") or {}
    ticket_ids = hotspots.get(risk_key) or []
    if not isinstance(ticket_ids, list):
        ticket_ids = []

    count = len(ticket_ids)

    # add bundle-level signal (from notes) as +1 if present
    bundle_risks = context_packet.get("bundle_level_risks") or []
    if isinstance(bundle_risks, list) and risk_key in bundle_risks:
        count += 1

    evidence_refs = [str(tid) for tid in ticket_ids]
    if risk_key in (bundle_risks or []):
        evidence_refs.append("bundle_notes")

    return count, evidence_refs


def _severity_from_count(count: int) -> str:
    if count >= 4:
        return "critical"
    if count >= 2:
        return "high"
    if count >= 1:
        return "medium"
    return "low"


def _decision_rank(policy: Dict[str, Any], decision: str) -> int:
    rank = policy.get("decision_rank") or {}
    return int(rank.get(decision, 0))


def run(
    context_packet: Dict[str, Any],
    findings_requirements: Optional[Dict[str, Any]] = None,
    policies: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Produces findings_risk.json using:
      - context_packet risk_hotspots + bundle_level_risks (from Intake)
      - (optional) findings_requirements text to detect if mitigations already exist
      - policies/guardrails.yaml for deterministic gating decision
    """
    policy = policies or _load_policy()
    corpus = _text_corpus(findings_requirements)

    bundle_id = str(context_packet.get("bundle_id", "unknown"))
    risk_category_map = policy.get("risk_category_map") or {}
    mitigation_keywords = policy.get("mitigation_keywords") or {}

    # Which risks are present?
    present_risks: List[str] = []
    hotspots = context_packet.get("risk_hotspots") or {}
    for k, v in hotspots.items():
        if isinstance(v, list) and len(v) > 0:
            present_risks.append(str(k))
    for k in (context_packet.get("bundle_level_risks") or []):
        if k not in present_risks:
            present_risks.append(str(k))

    # Build risk objects
    risks_out: List[Dict[str, Any]] = []
    for idx, risk_key in enumerate(sorted(set(present_risks)), start=1):
        evidence_count, evidence_refs = _count_evidence(context_packet, risk_key)
        category = str(risk_category_map.get(risk_key, "other"))
        severity = _severity_from_count(evidence_count)

        desc = {
            "privacy": "Privacy risk: billing data handling, GDPR/PII concerns, retention/residency requirements.",
            "auth": "Security risk: login/MFA failures or auth flow regressions affecting billing/checkout.",
            "accessibility": "Accessibility risk: WCAG issues (screen reader labels, keyboard navigation, focus states).",
            "pricing": "Compliance risk: billing/pricing clarity impacting invoices, refunds, and auditability.",
            "platform": "Platform risk: cross-platform/browser or SDK integration constraints.",
        }.get(risk_key, "Risk identified from bundle evidence.")

        risks_out.append(
            {
                "id": f"RISK-{idx:03d}",
                "category": category,
                "source_risk": risk_key,
                "severity": severity,
                "description": desc,
                "evidence_refs": evidence_refs,
            }
        )

    # Evaluate guardrail rules
    triggered: List[RuleResult] = []
    for rule in policy.get("rules", []) or []:
        rule_id = str(rule.get("id", "rule"))
        when = rule.get("when") or {}
        risk_key = str(when.get("risk", "")).strip()
        min_evidence = int(when.get("min_evidence", 1))
        required_keys = when.get("require_mitigations") or []
        required_keys = [str(x) for x in required_keys]

        if not risk_key:
            continue

        evidence_count, _ = _count_evidence(context_packet, risk_key)
        if evidence_count < min_evidence:
            continue

        # which mitigation keys are satisfied by corpus?
        missing_keys: List[str] = []
        for mk in required_keys:
            kws = mitigation_keywords.get(mk) or []
            kws = [str(k).lower() for k in kws]
            if not kws:
                missing_keys.append(mk)
                continue
            if not any(kw in corpus for kw in kws):
                missing_keys.append(mk)

        if missing_keys:
            triggered.append(
                RuleResult(
                    rule_id=rule_id,
                    decision=str(rule.get("decision", policy.get("default_decision", "Proceed"))),
                    matched_risk=risk_key,
                    evidence_count=evidence_count,
                    missing_mitigation_keys=missing_keys,
                    required_mitigations=[str(x) for x in (rule.get("required_mitigations") or [])],
                )
            )

    # Choose final decision (most conservative)
    final_decision = str(policy.get("default_decision", "Proceed"))
    for rr in triggered:
        if _decision_rank(policy, rr.decision) > _decision_rank(policy, final_decision):
            final_decision = rr.decision

    # Collect required mitigations (unique)
    mitigations: List[str] = []
    for rr in triggered:
        for m in rr.required_mitigations:
            if m and m not in mitigations:
                mitigations.append(m)

    policy_eval = [
        {
            "rule_id": rr.rule_id,
            "risk": rr.matched_risk,
            "decision": rr.decision,
            "evidence_count": rr.evidence_count,
            "missing_mitigation_keys": rr.missing_mitigation_keys,
        }
        for rr in triggered
    ]

    return {
        "bundle_id": bundle_id,
        "generated_at": _now_iso(),
        "gating_decision": final_decision,
        "risks": risks_out,
        "required_mitigations": mitigations,
        "policy_pack": {
            "version": str(policy.get("version", "unknown")),
            "applied_rule_ids": [x["rule_id"] for x in policy_eval],
        },
        "policy_evaluation": policy_eval,
        "warnings": [],
    }