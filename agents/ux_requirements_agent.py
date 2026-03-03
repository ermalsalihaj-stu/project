from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List

@dataclass
class Journey:
    id: str
    name: str
    type: str
    persona: str
    steps: List[Dict[str, Any]]
    pain_points: List[str]
    success_criteria: List[str]
    related_ticket_ids: List[str]

@dataclass
class Requirement:
    id: str
    title: str
    statement: str
    priority: str
    rationale: str
    acceptance_criteria: List[str]
    related_ticket_ids: List[str]
    related_journey_ids: List[str]

@dataclass
class EdgeCase:
    id: str
    description: str
    category: str
    linked_requirements: List[str]


def _extract_ticket_ids(context_packet: dict) -> List[str]:
    tickets = context_packet.get("tickets") or []
    ids: List[str] = []
    for t in tickets:
        tid = t.get("id")
        if isinstance(tid, str):
            ids.append(tid)
    return ids

def _build_default_journeys(context_packet: dict) -> List[Journey]:
    ticket_ids = _extract_ticket_ids(context_packet)
    first_two = ticket_ids[:2]

    happy = Journey(
        id="J-001",
        name="Happy path – user completes primary task",
        type="happy_path",
        persona="Primary user",
        steps=[
            {
                "order": 1,
                "actor": "user",
                "action": "Starts from the main entry point and initiates the primary task.",
                "system_response": "System loads the relevant screen quickly with contextual guidance.",
            },
            {
                "order": 2,
                "actor": "user",
                "action": "Provides required information with minimal friction.",
                "system_response": "System validates inputs inline and shows clear progress.",
            },
            {
                "order": 3,
                "actor": "user",
                "action": "Confirms the operation.",
                "system_response": "System completes the flow, shows confirmation, and highlights next best actions.",
            },
        ],
        pain_points=[
            "Too many steps or unclear progress through the flow.",
            "Inline validation and feedback are inconsistent or missing.",
        ],
        success_criteria=[
            "User can complete the primary flow in one attempt without confusion.",
            "System provides clear confirmation and next steps.",
        ],
        related_ticket_ids=first_two,
    )

    failure = Journey(
        id="J-002",
        name="Failure path – user hits an error or edge case",
        type="edge_path",
        persona="Primary user",
        steps=[
            {
                "order": 1,
                "actor": "user",
                "action": "Attempts to perform the primary task with incomplete or invalid data.",
                "system_response": "System detects the issue and surfaces a clear, actionable error message.",
            },
            {
                "order": 2,
                "actor": "user",
                "action": "Adjusts inputs based on guidance.",
                "system_response": "System re-validates and lets the user continue without losing prior work.",
            },
            {
                "order": 3,
                "actor": "system",
                "action": "Handles timeouts or transient failures.",
                "system_response": "System retries safely or offers a non-destructive fallback path.",
            },
        ],
        pain_points=[
            "Errors are generic or do not explain how to recover.",
            "User loses progress when something goes wrong.",
        ],
        success_criteria=[
            "Users can recover from common errors without contacting support.",
            "No data is lost when retries or recovery flows are triggered.",
        ],
        related_ticket_ids=ticket_ids[2:5],
    )

    return [happy, failure]


def _build_requirements(journeys: List[Journey], context_packet: dict) -> List[Requirement]:
    all_ticket_ids = _extract_ticket_ids(context_packet)

    def ac(text: str) -> str:
        return text

    reqs: List[Requirement] = []

    reqs.append(
        Requirement(
            id="REQ-001",
            title="Primary flow is clearly guided end-to-end",
            statement="User can complete the primary flow with clear guidance, minimal steps, and visible progress.",
            priority="Must",
            rationale="Reduces drop-off and confusion in the core experience.",
            acceptance_criteria=[
                ac("Given a new or returning user, When they start the primary flow, Then they see a clear indicator of how many steps remain."),
                ac("Given a user in the middle of the flow, When they move to the next step, Then the system preserves prior inputs without data loss."),
            ],
            related_ticket_ids=all_ticket_ids[:3],
            related_journey_ids=[journeys[0].id],
        )
    )

    reqs.append(
        Requirement(
            id="REQ-002",
            title="Inline validation and actionable error messages",
            statement="System validates inputs inline and provides actionable, context-specific errors.",
            priority="Must",
            rationale="Prevents user frustration and reduces support tickets.",
            acceptance_criteria=[
                ac("Given a required field is left empty, When the user attempts to continue, Then the system highlights the field and explains what is missing."),
                ac("Given an invalid value is entered, When validation fails, Then the error explains how to correct it without using technical jargon."),
            ],
            related_ticket_ids=all_ticket_ids[3:6],
            related_journey_ids=[journeys[0].id, journeys[1].id],
        )
    )

    reqs.append(
        Requirement(
            id="REQ-003",
            title="Resilient handling of timeouts and transient failures",
            statement="System handles timeouts, network issues, and transient failures without data loss.",
            priority="Should",
            rationale="Improves reliability and trust, especially on slower networks.",
            acceptance_criteria=[
                ac("Given a transient network error occurs during submission, When the user retries, Then the system reuses already entered data and does not double-submit."),
                ac("Given a long-running operation, When it exceeds a safe time limit, Then the user sees a clear message and a safe retry or cancel option."),
            ],
            related_ticket_ids=all_ticket_ids[6:],
            related_journey_ids=[journeys[1].id],
        )
    )

    reqs.append(
        Requirement(
            id="REQ-004",
            title="Accessible experience for assistive technologies",
            statement="The primary flow meets baseline accessibility requirements for screen readers and keyboard navigation.",
            priority="Must",
            rationale="Prevents exclusion of users who rely on assistive technologies and reduces accessibility risk.",
            acceptance_criteria=[
                ac("Given a user navigates with a keyboard only, When they move through the primary flow, Then focus order is logical and all interactive elements are reachable."),
                ac("Given a user relies on a screen reader, When they encounter form fields, Then labels and error messages are announced clearly."),
            ],
            related_ticket_ids=all_ticket_ids,
            related_journey_ids=[j.id for j in journeys],
        )
    )

    reqs.append(
        Requirement(
            id="REQ-005",
            title="Clear confirmation and next-best actions",
            statement="After successful completion, the user sees confirmation plus next-best actions.",
            priority="Should",
            rationale="Makes success state obvious and encourages further engagement.",
            acceptance_criteria=[
                ac("Given a user successfully completes the primary flow, When the confirmation screen appears, Then it clearly states the outcome in plain language."),
                ac("Given the confirmation screen is shown, When relevant next actions exist, Then the system surfaces at least one recommended follow-up action."),
            ],
            related_ticket_ids=all_ticket_ids[:4],
            related_journey_ids=[journeys[0].id],
        )
    )

    reqs.append(
        Requirement(
            id="REQ-006",
            title="Auditability of critical user actions",
            statement="Critical user actions in the primary flow are traceable for troubleshooting and support.",
            priority="Could",
            rationale="Helps debug issues and connects UX to metrics and risk analysis.",
            acceptance_criteria=[
                ac("Given a user completes the primary flow, When support investigates a related issue, Then they can see a basic event trail for that flow without exposing sensitive data."),
            ],
            related_ticket_ids=all_ticket_ids,
            related_journey_ids=[j.id for j in journeys],
        )
    )

    return reqs

def _build_edge_cases(requirements: List[Requirement]) -> List[EdgeCase]:
    linked = {r.id for r in requirements}

    def lr(*ids: str) -> List[str]:
        return [i for i in ids if i in linked]

    return [
        EdgeCase(
            id="EC-001",
            description="User loses network connectivity mid-flow.",
            category="offline",
            linked_requirements=lr("REQ-003"),
        ),
        EdgeCase(
            id="EC-002",
            description="User attempts to proceed with multiple required fields empty.",
            category="input_validation",
            linked_requirements=lr("REQ-002"),
        ),
        EdgeCase(
            id="EC-003",
            description="System times out while processing a long-running operation.",
            category="timeout",
            linked_requirements=lr("REQ-003"),
        ),
        EdgeCase(
            id="EC-004",
            description="User navigates only with keyboard and cannot reach a critical control.",
            category="accessibility",
            linked_requirements=lr("REQ-004"),
        ),
        EdgeCase(
            id="EC-005",
            description="Error message is displayed but does not explain how to fix the issue.",
            category="input_validation",
            linked_requirements=lr("REQ-002"),
        ),
        EdgeCase(
            id="EC-006",
            description="Critical user actions are not logged, making it hard to reconstruct what happened.",
            category="other",
            linked_requirements=lr("REQ-006"),
        ),
        EdgeCase(
            id="EC-007",
            description="User refreshes the page mid-flow and loses all previously entered data.",
            category="other",
            linked_requirements=lr("REQ-001", "REQ-003"),
        ),
        EdgeCase(
            id="EC-008",
            description="User abandons the flow after reaching the confirmation step because the success state is unclear.",
            category="other",
            linked_requirements=lr("REQ-005"),
        ),
    ]

def _build_backlog(requirements: List[Requirement]) -> Dict[str, Any]:
    epics = [
        {
            "id": "EP-1",
            "title": "Streamlined primary user flow",
            "description": "Design and implement a guided, low-friction primary flow for the core experience.",
            "priority": "Must",
        },
        {
            "id": "EP-2",
            "title": "Resilience, accessibility, and error handling",
            "description": "Make the experience resilient to failures and accessible to assistive technologies.",
            "priority": "Must",
        },
        {
            "id": "EP-3",
            "title": "Confirmation, next steps, and instrumentation",
            "description": "Clarify success states, surface next-best actions, and ensure basic auditability.",
            "priority": "Should",
        },
    ]

    def story(
        sid: str,
        title: str,
        description: str,
        epic_id: str,
        priority: str,
        ac_list: List[str],
        linked_reqs: List[str],
        deps: List[str] | None = None,
    ) -> Dict[str, Any]:
        return {
            "id": sid,
            "title": title,
            "description": description,
            "epic_id": epic_id,
            "priority": priority,
            "acceptance_criteria": ac_list,
            "linked_requirements": linked_reqs,
            "dependencies": deps or [],
        }

    stories = [
        story(
            "ST-001",
            "Add clear step indicator to primary flow",
            "Show users where they are and how many steps remain in the primary flow.",
            "EP-1",
            "Must",
            [
                "Given a user starts the primary flow, When they progress between steps, Then the step indicator updates to reflect their position.",
            ],
            ["REQ-001"],
        ),
        story(
            "ST-002",
            "Implement inline validation for critical fields",
            "Validate critical inputs inline and explain how to fix errors.",
            "EP-1",
            "Must",
            [
                "Given a required field is left empty, When the user moves focus away, Then the field is marked invalid with a clear message.",
            ],
            ["REQ-002"],
        ),
        story(
            "ST-003",
            "Handle transient failures without data loss",
            "Ensure that transient failures and timeouts do not cause data loss in the flow.",
            "EP-2",
            "Should",
            [
                "Given a transient failure occurs, When the user retries, Then previously entered data is preserved.",
            ],
            ["REQ-003"],
            deps=["ST-001"],
        ),
        story(
            "ST-004",
            "Keyboard and screen reader accessibility for primary flow",
            "Bring the primary flow to baseline accessibility for keyboard and screen reader users.",
            "EP-2",
            "Must",
            [
                "Given a user navigates only with a keyboard, When they move through the flow, Then all interactive elements are reachable in a logical order.",
            ],
            ["REQ-004"],
        ),
        story(
            "ST-005",
            "Design clear confirmation screen",
            "Design and implement a confirmation screen that clearly communicates success and next steps.",
            "EP-3",
            "Should",
            [
                "Given a user completes the primary flow, When the confirmation screen is shown, Then the success message and next steps are obvious.",
            ],
            ["REQ-005"],
            deps=["ST-001"],
        ),
        story(
            "ST-006",
            "Add basic event-level audit trail for the flow",
            "Capture a minimal event trail for the primary flow to support troubleshooting.",
            "EP-3",
            "Could",
            [
                "Given support investigates a completed flow, When they inspect the event log, Then they can see a sequence of key actions without sensitive payloads.",
            ],
            ["REQ-006"],
        ),
    ]

    return {
        "epics": epics,
        "stories": stories,
    }

def run(context_packet: dict) -> dict:
    """
    Agent E - UX & Requirements.

    Convert context_packet into:
      - journeys (happy path + edge/failure path)
      - requirements with acceptance criteria
      - edge cases linked to requirements
      - backlog candidates (epics + stories)
    """

    bundle_id = context_packet.get("bundle_id", "")
    summary = context_packet.get("request_summary") or ""

    journeys = _build_default_journeys(context_packet)
    requirements = _build_requirements(journeys, context_packet)
    edge_cases = _build_edge_cases(requirements)
    backlog = _build_backlog(requirements)

    return {
        "bundle_id": bundle_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "journeys": [
            {
                "id": j.id,
                "name": j.name,
                "type": j.type,
                "persona": j.persona,
                "steps": j.steps,
                "pain_points": j.pain_points,
                "success_criteria": j.success_criteria,
                "related_ticket_ids": j.related_ticket_ids,
            }
            for j in journeys
        ],
        "requirements": [
            {
                "id": r.id,
                "title": r.title,
                "statement": r.statement,
                "priority": r.priority,
                "rationale": r.rationale,
                "acceptance_criteria": r.acceptance_criteria,
                "related_ticket_ids": r.related_ticket_ids,
                "related_journey_ids": r.related_journey_ids,
            }
            for r in requirements
        ],
        "edge_cases": [
            {
                "id": e.id,
                "description": e.description,
                "category": e.category,
                "linked_requirements": e.linked_requirements,
            }
            for e in edge_cases
        ],
        "backlog": backlog,
    }

