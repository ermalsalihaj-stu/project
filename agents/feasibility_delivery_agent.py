from __future__ import annotations
from typing import Any

def run(context_packet: dict, findings_requirements: dict | None = None) -> dict:
   
    bundle_id = context_packet.get("bundle_id", "unknown")
    request_summary = (context_packet.get("request_summary") or "").lower()
    tickets = context_packet.get("tickets") or []
    metrics_snapshot = context_packet.get("metrics_snapshot") or {}
    risk_hotspots = context_packet.get("risk_hotspots") or {}

    dependencies = _derive_dependencies(
        request_summary=request_summary,
        tickets=tickets,
        metrics_snapshot=metrics_snapshot,
        risk_hotspots=risk_hotspots,
    )
    constraints = _derive_constraints(
        request_summary=request_summary,
        metrics_snapshot=metrics_snapshot,
        risk_hotspots=risk_hotspots,
    )
    complexity = _derive_complexity(
        request_summary=request_summary,
        tickets=tickets,
        risk_hotspots=risk_hotspots,
        findings_requirements=findings_requirements,
        dependencies=dependencies,
    )
    phases = _plan_phases(
        findings_requirements=findings_requirements,
        dependencies=dependencies,
        complexity=complexity,
    )
    build_vs_buy_triggers = _build_vs_buy_triggers(dependencies, complexity, constraints)

    return {
        "bundle_id": bundle_id,
        "dependencies": dependencies,
        "constraints": constraints,
        "complexity": complexity,
        "phases": phases,
        "build_vs_buy_triggers": build_vs_buy_triggers,
    }


def _text_from_tickets(tickets: list[dict]) -> str:
    parts: list[str] = []
    for t in tickets:
        title = t.get("title") or ""
        desc = t.get("description") or ""
        parts.append(str(title))
        parts.append(str(desc))
    return " ".join(parts).lower()


def _derive_dependencies(
    request_summary: str,
    tickets: list[dict],
    metrics_snapshot: dict,
    risk_hotspots: dict,
) -> list[dict[str, Any]]:
    """Heuristic dependency list based on domain cues in context."""
    text = f"{request_summary} {_text_from_tickets(tickets)}"
    deps: list[dict[str, Any]] = []

    def add_dep(
        dep_id: str,
        name: str,
        category: str,
        description: str,
        criticality: str = "Must",
        phases: list[str] | None = None,
        build_vs_buy_hint: str | None = None,
    ) -> None:
        if any(d["id"] == dep_id for d in deps):
            return
        deps.append(
            {
                "id": dep_id,
                "name": name,
                "category": category,
                "description": description,
                "criticality": criticality,
                "phases": phases or [],
                "build_vs_buy_hint": build_vs_buy_hint or "",
            }
        )

    if any(k in text for k in ["payment", "billing", "checkout", "invoice", "pricing"]):
        add_dep(
            "DEP-payment-provider",
            "Payment provider / PSP",
            "payment",
            "Integrate with a payment service provider (e.g. Stripe, Adyen, Braintree) for card and alternative payment methods.",
            criticality="Must",
            phases=["MVP", "V1"],
            build_vs_buy_hint="If you need global coverage, multiple payment methods, and PCI scope reduction, prefer a vendor PSP.",
        )

    if any(k in text for k in ["sso", "single sign-on", "saml", "oauth", "oidc", "okta", "azure ad", "login", "authentication"]):
        add_dep(
            "DEP-auth-sso",
            "Auth & SSO provider",
            "auth_sso",
            "Central authentication and single sign-on integration (e.g. Okta, Azure AD, Auth0).",
            criticality="Must",
            phases=["MVP", "V1"],
            build_vs_buy_hint="If enterprise SSO, audit trails, and policies are required, lean towards an IDaaS vendor.",
        )

    if any(k in text for k in ["schema", "migration", "database", "table", "column", "entity", "data model"]):
        add_dep(
            "DEP-db-migrations",
            "Application database & migrations",
            "data_store",
            "Relational or document store plus migration tooling to support new entities and relationships.",
            criticality="Must",
            phases=["MVP", "V1"],
            build_vs_buy_hint="Use existing DB platform; avoid bespoke storage unless scale or latency truly require it.",
        )

    has_metrics_snapshot = bool(metrics_snapshot)
    if has_metrics_snapshot or any(k in text for k in ["event", "tracking", "analytics", "telemetry", "instrumentation"]):
        add_dep(
            "DEP-analytics",
            "Product analytics instrumentation",
            "analytics",
            "Client/server SDK for event collection, funnels, and guardrail metrics.",
            criticality="Should",
            phases=["MVP", "V1", "V2"],
            build_vs_buy_hint="If you need self-service funnels and cohorting, use an analytics vendor (e.g. Amplitude, Mixpanel) rather than building charts.",
        )
    if any(k in text for k in ["async", "queue", "stream", "event bus", "kafka", "pubsub", "background job"]):
        add_dep(
            "DEP-queue",
            "Async processing / queue",
            "queue_stream",
            "Queue or stream for background processing of non-critical or heavy tasks.",
            criticality="Should",
            phases=["V1", "V2"],
            build_vs_buy_hint="Managed queue (e.g. SQS, Pub/Sub) usually beats running bespoke queue infra.",
        )

    if any(k in text for k in ["integration", "webhook", "api", "third-party", "external system", "partner"]):
        add_dep(
            "DEP-external-api",
            "External API integrations",
            "external_api",
            "Integrations with partner or third-party APIs via stable contracts and webhooks.",
            criticality="Should",
            phases=["V1", "V2"],
            build_vs_buy_hint="Use standard SDKs and integration platforms where possible, rather than custom one-off connectors.",
        )

    if "latency" in risk_hotspots or "performance" in risk_hotspots:
        add_dep(
            "DEP-infra-observability",
            "Infra & observability stack",
            "infrastructure",
            "Logging, tracing, and metrics for core flows, with alerts on latency and error budgets.",
            criticality="Should",
            phases=["MVP", "V1", "V2"],
            build_vs_buy_hint="Prefer managed APM/observability platforms instead of rolling custom tracing.",
        )

    if not deps:
        add_dep(
            "DEP-platform-basics",
            "Core application platform",
            "infrastructure",
            "Existing app platform (web/app server, database, logging) assumed as baseline dependency.",
            criticality="Must",
            phases=["MVP", "V1", "V2"],
            build_vs_buy_hint="Reuse current platform where possible; avoid premature re-platforming for MVP.",
        )

    return deps


def _derive_constraints(
    request_summary: str,
    metrics_snapshot: dict,
    risk_hotspots: dict,
) -> list[dict[str, Any]]:
    """Key constraints: latency, retention, permissions, compliance, platform."""
    constraints: list[dict[str, Any]] = []
    text = request_summary
    has_latency_metric = any(
        isinstance(m, str) and "latency" in m.lower()
        for m in (metrics_snapshot.get("guardrails") or {}).keys()
    ) or "latency" in text

    def add(
        ctype: str,
        description: str,
        phase_impact: list[str] | None = None,
    ) -> None:
        constraints.append(
            {
                "type": ctype,
                "description": description,
                "phase_impact": phase_impact or [],
            }
        )

    if has_latency_metric or "performance" in (risk_hotspots or {}):
        add(
            "latency",
            "Critical user paths require predictable latency; set p95 targets and error budgets for core flows.",
            ["MVP", "V1", "V2"],
        )

    if any(k in text for k in ["audit", "history", "log", "retention", "archiv"]):
        add(
            "data_retention",
            "Need explicit retention policy for logs, events, and PII, aligned with legal/privacy requirements.",
            ["V1", "V2"],
        )

    if any(k in text for k in ["role", "permission", "rbac", "admin", "entitlement"]):
        add(
            "permissions",
            "Role-based access control and permission checks must gate admin or sensitive operations.",
            ["MVP", "V1"],
        )

    if any(k in (risk_hotspots or {}) for k in ["privacy", "gdpr", "hipaa", "pci", "pii"]):
        add(
            "compliance",
            "Privacy/compliance constraints (e.g. GDPR, PCI, PII minimization) apply to storage and processing of user data.",
            ["MVP", "V1", "V2"],
        )

    if any(k in text for k in ["mobile", "ios", "android", "browser", "extension", "plugin"]):
        add(
            "platform",
            "Client platform capabilities and store policies limit what can be shipped (e.g. mobile vs web parity, browser support).",
            ["MVP", "V1", "V2"],
        )

    if not constraints:
        add(
            "other",
            "Existing platform, release cadence, and team capacity constrain scope per phase; prioritize smallest viable slice for MVP.",
            ["MVP"],
        )

    return constraints


def _derive_complexity(
    request_summary: str,
    tickets: list[dict],
    risk_hotspots: dict,
    findings_requirements: dict | None,
    dependencies: list[dict],
) -> list[dict[str, Any]]:
    """Assign Low/Medium/High buckets to key topics with reasons."""
    text = f"{request_summary} {_text_from_tickets(tickets)}"
    complexity: list[dict[str, Any]] = []

    def add(topic: str, bucket: str, reason: str, related_deps: list[str] | None = None, related_reqs: list[str] | None = None) -> None:
        complexity.append(
            {
                "topic": topic,
                "bucket": bucket,
                "reason": reason,
                "related_dependencies": related_deps or [],
                "related_requirements": related_reqs or [],
            }
        )

    dep_ids = {d["id"]: d for d in dependencies}

    def dep_present(prefix: str) -> bool:
        return any(did.startswith(prefix) for did in dep_ids)

    reqs = (findings_requirements or {}).get("requirements") or []
    must_reqs = [r for r in reqs if (r.get("priority") or "").lower() == "must"]
    total_reqs = len(reqs)

    if dep_present("DEP-payment"):
        bucket = "Medium"
        if "billing" in (risk_hotspots or {}) or any("refund" in (t.get("title", "").lower() + t.get("description", "").lower()) for t in tickets):
            bucket = "High"
        add(
            "payments & billing",
            bucket,
            "Integration with payment provider plus edge cases like retries, failures, and refunds.",
            related_deps=["DEP-payment-provider"],
        )

    if dep_present("DEP-auth-sso"):
        bucket = "Medium"
        if any(k in (risk_hotspots or {}) for k in ["auth", "security"]):
            bucket = "High"
        add(
            "auth & SSO",
            bucket,
            "Enterprise SSO, provisioning flows, and session management increase integration and testing effort.",
            related_deps=["DEP-auth-sso"],
        )

    if dep_present("DEP-db-migrations"):
        bucket = "Medium" if total_reqs <= 10 else "High"
        add(
            "data model & migrations",
            bucket,
            "New entities/relationships and online migrations across environments.",
            related_deps=["DEP-db-migrations"],
        )

    if dep_present("DEP-analytics"):
        add(
            "analytics & instrumentation",
            "Medium",
            "Event taxonomy, tag propagation, and validation across client and server.",
            related_deps=["DEP-analytics"],
        )

    if dep_present("DEP-infra-observability"):
        add(
            "infra & observability",
            "Medium",
            "Dashboards, alerts, and tracing to support SLOs for latency and errors.",
            related_deps=["DEP-infra-observability"],
        )

    if total_reqs:
        overall_bucket = "Low"
        if total_reqs > 12 or len(must_reqs) > 6:
            overall_bucket = "High"
        elif total_reqs > 6 or len(must_reqs) > 3:
            overall_bucket = "Medium"
        add(
            "overall implementation scope",
            overall_bucket,
            f"{total_reqs} total requirements with {len(must_reqs)} Must-haves drive overall build complexity.",
        )

    if not complexity:
        add(
            "overall implementation scope",
            "Low",
            "Small, self-contained feature with limited external dependencies inferred from context.",
        )

    return complexity


def _plan_phases(
    findings_requirements: dict | None,
    dependencies: list[dict],
    complexity: list[dict],
) -> dict[str, Any]:
    reqs = (findings_requirements or {}).get("requirements") or []
    in_scope_mvp: list[str] = []
    in_scope_v1: list[str] = []
    in_scope_v2: list[str] = []

    if reqs:
        for r in reqs:
            rid = r.get("id") or r.get("title") or ""
            priority = (r.get("priority") or "").lower()
            if not rid:
                continue
            if priority == "must":
                in_scope_mvp.append(rid)
            elif priority == "should":
                in_scope_v1.append(rid)
            else:
                in_scope_v2.append(rid)

    if not (in_scope_mvp or in_scope_v1 or in_scope_v2):
        in_scope_mvp = ["Core happy-path flow and basic instrumentation"]
        in_scope_v1 = ["Edge cases, resilience, and admin tooling"]
        in_scope_v2 = ["Advanced optimization, automation, and reporting"]

    dep_ids_must = [d["id"] for d in dependencies if (d.get("criticality") == "Must")]
    dep_ids_should = [d["id"] for d in dependencies if (d.get("criticality") == "Should")]

    mvp_prereq = [f"Dependency ready: {d}" for d in dep_ids_must]
    v1_prereq = [f"Dependency ready: {d}" for d in dep_ids_should]

    has_high = any(c.get("bucket") == "High" for c in complexity)
    if has_high and not isinstance(in_scope_mvp[0], str):
    
        pass

    phases: dict[str, Any] = {
        "MVP": {
            "in_scope": in_scope_mvp,
            "out_of_scope": in_scope_v1 + in_scope_v2,
            "prerequisites": mvp_prereq,
        },
        "V1": {
            "in_scope": in_scope_v1,
            "out_of_scope": in_scope_v2,
            "prerequisites": v1_prereq + ["MVP learnings incorporated"],
        },
        "V2": {
            "in_scope": in_scope_v2,
            "out_of_scope": [],
            "prerequisites": ["MVP and V1 adoption/impact reviewed"],
        },
    }

    return phases


def _build_vs_buy_triggers(
    dependencies: list[dict],
    complexity: list[dict],
    constraints: list[dict],
) -> list[dict[str, Any]]:
    """Explicit triggers for considering vendors vs in-house builds."""
    triggers: list[dict[str, Any]] = []

    def add(condition: str, recommendation: str, related_topic: str | None = None) -> None:
        triggers.append(
            {
                "condition": condition,
                "recommendation": recommendation,
                "related_topic": related_topic or "",
            }
        )

    topics_by_name = {c["topic"]: c for c in complexity}
    constraint_types = {c["type"] for c in constraints}
    dep_categories = {d["category"] for d in dependencies}

    if "payment" in dep_categories:
        bucket = topics_by_name.get("payments & billing", {}).get("bucket", "Medium")
        add(
            "If you need PCI compliance, multiple payment methods, or global tax handling.",
            "Use a mature PSP and tax/compliance vendor instead of building payment processing and billing from scratch.",
            "payments & billing",
        )
        if bucket == "High":
            add(
                "If refunds, chargebacks, and complex invoicing are in-scope.",
                "Prioritize vendors with strong dispute management and invoicing APIs.",
                "payments & billing",
            )

    if "auth_sso" in dep_categories:
        add(
            "If enterprise customers require SSO, SCIM, and detailed audit trails.",
            "Adopt an IDaaS platform (e.g. Okta, Azure AD, Auth0) instead of custom auth stacks.",
            "auth & SSO",
        )

    if "analytics" in dep_categories:
        add(
            "If PMs need self-serve funnels, cohorts, and experiment analysis.",
            "Use a product analytics vendor rather than building charting and query tooling in-house.",
            "analytics & instrumentation",
        )

    if "latency" in constraint_types or "availability" in constraint_types:
        add(
            "If uptime and latency SLOs are strict but observability is weak.",
            "Adopt a managed logging/APM platform instead of building bespoke tracing and dashboards.",
            "infra & observability",
        )

    if "compliance" in constraint_types or "data_retention" in constraint_types:
        add(
            "If regulated data (PII, payment data, health data) is stored long-term.",
            "Consider specialized vendors for vaulting, key management, and compliant storage instead of rolling your own.",
            "data model & migrations",
        )
    if not triggers:
        add(
            "If an area is High complexity with limited in-house expertise.",
            "Start with a vendor or managed service, then revisit in-house builds only if clear cost/strategic upside emerges.",
            "overall implementation scope",
        )

    return triggers

