from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

from tools.io_utils import read_json, read_text, write_json


@dataclass
class LoadedBundle:
    bundle_id: str
    bundle_path: Path
    manifest: dict
    request_text: str
    tickets_raw: list
    customer_notes: str
    metrics_snapshot: dict
    competitors: str
    warnings: list


def _safe_read_optional_text(p: Path, warnings: list, label: str) -> str:
    if not p.exists():
        warnings.append(f"Missing optional file: {label} ({p.as_posix()})")
        return ""
    return read_text(p)


def _safe_read_optional_json(p: Path, warnings: list, label: str) -> Any:
    if not p.exists():
        warnings.append(f"Missing optional file: {label} ({p.as_posix()})")
        return {}
    try:
        return read_json(p)
    except Exception as e:
        warnings.append(f"Failed to parse JSON for {label} ({p.as_posix()}): {e}")
        return {}


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_bundle(bundle_path: str | Path) -> LoadedBundle:
    bp = Path(bundle_path)
    manifest_path = bp / "bundle_manifest.json"

    warnings: list[str] = []
    if not manifest_path.exists():
        raise FileNotFoundError(f"bundle_manifest.json not found at: {manifest_path.as_posix()}")

    manifest = read_json(manifest_path)
    bundle_id = manifest.get("bundle_id") or bp.name

    files = manifest.get("files", {})
    # këto janë “labels” që Intern 2 pritet me i mbushë; nëse mungojnë s’bëjm crash
    request_rel = files.get("request", "product_request.md")
    tickets_rel = files.get("tickets", "tickets.json")
    notes_rel = files.get("customer_notes", "customer_notes.md")
    metrics_rel = files.get("metrics_snapshot", "metrics_snapshot.json")
    competitors_rel = files.get("competitors", "competitors.md")

    request_text = _safe_read_optional_text(bp / request_rel, warnings, "request")
    customer_notes = _safe_read_optional_text(bp / notes_rel, warnings, "customer_notes")
    competitors = _safe_read_optional_text(bp / competitors_rel, warnings, "competitors")
    metrics_snapshot = _safe_read_optional_json(bp / metrics_rel, warnings, "metrics_snapshot")

    tickets_path = bp / tickets_rel
    tickets_raw: list = []
    if tickets_path.exists():
        if tickets_path.suffix.lower() == ".json":
            data = _safe_read_optional_json(tickets_path, warnings, "tickets")
            if isinstance(data, list):
                tickets_raw = data
            elif isinstance(data, dict) and "tickets" in data and isinstance(data["tickets"], list):
                tickets_raw = data["tickets"]
            else:
                warnings.append("tickets.json format unexpected (expected list or {tickets: [...]})")
        elif tickets_path.suffix.lower() == ".csv":
            try:
                with tickets_path.open("r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    tickets_raw = list(reader)
            except Exception as e:
                warnings.append(f"Failed to parse tickets.csv: {e}")
        else:
            warnings.append(f"Unsupported tickets file type: {tickets_path.suffix}")
    else:
        warnings.append(f"Missing tickets file: {tickets_path.as_posix()}")

    return LoadedBundle(
        bundle_id=bundle_id,
        bundle_path=bp,
        manifest=manifest,
        request_text=request_text,
        tickets_raw=tickets_raw,
        customer_notes=customer_notes,
        metrics_snapshot=metrics_snapshot if isinstance(metrics_snapshot, dict) else {},
        competitors=competitors,
        warnings=warnings,
    )


def normalize_ticket(t: dict) -> dict:
    # prano disa variante field-esh
    tid = t.get("id") or t.get("key") or t.get("ticket_id") or t.get("Issue key")
    title = t.get("title") or t.get("summary") or t.get("name") or t.get("Summary") or ""
    desc = t.get("description") or t.get("details") or t.get("Description") or ""
    tags = t.get("tags") or t.get("labels") or []
    if isinstance(tags, str):
        tags = [x.strip() for x in tags.split(",") if x.strip()]

    priority = t.get("priority") or t.get("Priority") or None
    created_at = t.get("created_at") or t.get("Created") or None
    source = t.get("source") or "bundle"

    # ruaj edhe originalin (shumë e dobishme për debug)
    return {
        "id": tid,
        "title": str(title).strip(),
        "description": str(desc).strip(),
        "tags": tags if isinstance(tags, list) else [],
        "priority": priority,
        "created_at": created_at,
        "source": source,
        "_raw": t,
    }


def _title_key(title: str) -> str:
    s = title.lower().strip()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s


def dedupe_tickets(tickets: list[dict], similarity_threshold: float = 0.90) -> Tuple[list[dict], list[dict]]:
    deduped: list[dict] = []
    duplicates: list[dict] = []

    seen_ids: dict[str, int] = {}
    for t in tickets:
        tid = t.get("id")
        if tid and tid in seen_ids:
            duplicates.append({
                "kept_ticket_id": deduped[seen_ids[tid]].get("id"),
                "dropped_ticket_id": tid,
                "reason": "same_id",
            })
            continue
        if tid:
            seen_ids[tid] = len(deduped)
        deduped.append(t)

    # similarity on titles (candidate duplicates)
    final: list[dict] = []
    for t in deduped:
        tkey = _title_key(t.get("title", ""))
        merged = False
        for kept in final:
            kkey = _title_key(kept.get("title", ""))
            if not tkey or not kkey:
                continue
            sim = SequenceMatcher(None, tkey, kkey).ratio()
            if sim >= similarity_threshold:
                duplicates.append({
                    "kept_ticket_id": kept.get("id"),
                    "dropped_ticket_id": t.get("id"),
                    "reason": f"title_similarity_{sim:.2f}",
                })
                # MVP: s’po e bojm merge content; vetëm e flag-ojm si duplicate
                merged = True
                break
        if not merged:
            final.append(t)

    return final, duplicates


def apply_ignore_rules(tickets: list[dict], ignore_policy: dict) -> Tuple[list[dict], list[dict]]:
    ignore_tags = set([x.lower() for x in ignore_policy.get("ignore_tags", [])])
    kept: list[dict] = []
    ignored: list[dict] = []

    for t in tickets:
        tags = [str(x).lower() for x in (t.get("tags") or [])]
        if any(tag in ignore_tags for tag in tags):
            ignored.append({"ticket_id": t.get("id"), "reason": "ignore_tag", "tags": t.get("tags", [])})
        else:
            kept.append(t)

    return kept, ignored


def detect_missing_info(tickets: list[dict]) -> list[dict]:
    missing: list[dict] = []
    for t in tickets:
        desc = (t.get("description") or "").lower()
        title = (t.get("title") or "").lower()

        missing_fields: list[str] = []
        questions: list[str] = []

        # acceptance criteria heuristic
        if ("acceptance criteria" not in desc) and ("ac:" not in desc):
            missing_fields.append("acceptance_criteria")
            questions.append("What are the acceptance criteria (AC) for this ticket?")

        # impact heuristic
        if not any(k in desc for k in ["impact", "user impact", "so that", "value", "benefit"]):
            missing_fields.append("user_impact")
            questions.append("Who is impacted and what’s the user impact/value?")

        # persona/segment heuristic
        if not any(k in desc for k in ["persona", "segment", "role:", "as a "]):
            missing_fields.append("persona_or_segment")
            questions.append("Which persona/segment is this for?")

        # if title/desc too short
        if len(title.strip()) < 8 or len(desc.strip()) < 20:
            missing_fields.append("details_insufficient")
            questions.append("Can we add more context/details or repro steps?")

        if missing_fields:
            missing.append({
                "ticket_id": t.get("id"),
                "missing_fields": missing_fields,
                "suggested_questions": questions,
            })

    return missing


def risk_tagging(tickets: list[dict], customer_notes: str, risk_policy: dict) -> tuple[list[dict], dict, list[str]]:
    """
    Ticket-level risk tags come ONLY from the ticket text (title+description).
    Customer notes produce bundle-level risk signals (not attached to every ticket).
    Returns:
      - tickets_with_risk_tags
      - risk_hotspots: {risk_name: [ticket_ids...]} (ticket-only)
      - bundle_level_risks: [risk_names...] (notes-only)
    """
    notes = (customer_notes or "").lower()
    hotspots: dict[str, list] = {}

    def has_kw(text: str, kws: list[str]) -> bool:
        txt = (text or "").lower()
        return any(kw.lower() in txt for kw in kws)

    # 1) bundle-level risks from notes
    bundle_level_risks: list[str] = []
    for risk_name, keywords in (risk_policy or {}).items():
        if keywords and has_kw(notes, keywords):
            bundle_level_risks.append(risk_name)

    # 2) ticket-level risks from ticket text only
    out: list[dict] = []
    for t in tickets:
        text = f"{t.get('title','')} {t.get('description','')}"
        risk_tags: list[str] = []

        for risk_name, keywords in (risk_policy or {}).items():
            if keywords and has_kw(text, keywords):
                risk_tags.append(risk_name)
                hotspots.setdefault(risk_name, []).append(t.get("id"))

        t2 = dict(t)
        t2["risk_tags"] = risk_tags
        out.append(t2)

    return out, hotspots, bundle_level_risks


def build_evidence_index(bundle: LoadedBundle) -> dict:
    files = bundle.manifest.get("files", {})
    return {
        "bundle_id": bundle.bundle_id,
        "paths": {
            "manifest": "bundle_manifest.json",
            **files,
        },
        "warnings": bundle.warnings,
    }


def build_context_packet(bundle_path: str | Path) -> dict:
    bundle = load_bundle(bundle_path)

    ignore_policy = _load_yaml(Path("policies") / "ignore_rules.yaml")
    risk_policy = _load_yaml(Path("policies") / "risk_keywords.yaml")

    normalized = [normalize_ticket(t) for t in (bundle.tickets_raw or [])]

    filtered, ignored_items = apply_ignore_rules(normalized, ignore_policy)
    deduped, duplicates = dedupe_tickets(filtered, similarity_threshold=0.90)

    missing_info = detect_missing_info(deduped)
    deduped_with_risk, risk_hotspots, bundle_level_risks = risk_tagging(deduped, bundle.customer_notes, risk_policy)

    # request summary MVP: 1–2 rreshta nga request file
    req_summary = (bundle.request_text or "").strip().splitlines()
    req_summary = " ".join([x.strip() for x in req_summary if x.strip()][:3]).strip()

    context_packet = {
        "bundle_id": bundle.bundle_id,
        "request_summary": req_summary,
        "tickets": deduped_with_risk,
        "customer_notes_summary": (bundle.customer_notes or "").strip()[:600],
        "metrics_snapshot": bundle.metrics_snapshot or {},
        "competitors_summary": (bundle.competitors or "").strip()[:600],
        "risk_hotspots": risk_hotspots,
        "bundle_level_risks": bundle_level_risks,
        "missing_info": missing_info,
        "ignored_items": ignored_items,
        "duplicates": duplicates,
        "warnings": bundle.warnings,
    }

    return context_packet


def run(bundle_path: str | Path, out_dir: str | Path | None = None) -> dict:
    cp = build_context_packet(bundle_path)

    if out_dir is not None:
        out = Path(out_dir)
        write_json(out / "context_packet.json", cp)
        # opsionale por e dobishme
        bundle = load_bundle(bundle_path)
        write_json(out / "evidence_index.json", build_evidence_index(bundle))

    return cp