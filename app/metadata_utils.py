# app/metadata_utils.py
import json
import hashlib
import time
import uuid
from typing import Any, Dict, Tuple, List, Set

DEFAULT_SENSITIVE_SELECTORS = {"password", "pass", "token", "secret", "card", "ssn", "email"}

def _is_sensitive_selector(selector: str, custom_sensitive: Set[str] = None) -> bool:
    selector = (selector or "").lower()
    sensitive_keywords = set(DEFAULT_SENSITIVE_SELECTORS)
    if custom_sensitive:
        sensitive_keywords |= {s.lower() for s in custom_sensitive}
    return any(kw in selector for kw in sensitive_keywords)

def sanitize_events(events: List[Dict], custom_sensitive: Set[str] = None) -> Tuple[List[Dict], List[str]]:
    masked = set()
    sanitized = []
    for ev in events:
        ev_copy = {}
        for k in ("type", "selector", "action", "url", "tag", "text", "value", "meta", "name", "label", "parent_hierarchy", "sibling_tags"):
            if k in ev:
                ev_copy[k] = ev[k]
        if "value" in ev_copy and ev_copy["value"] is not None:
            if _is_sensitive_selector(ev_copy.get("selector", ""), custom_sensitive):
                masked.add(ev_copy.get("selector", ""))
            ev_copy["value"] = "<REDACTED>"
        if "selector" in ev_copy and isinstance(ev_copy["selector"], str):
            ev_copy["selector"] = ev_copy["selector"].strip()
        sanitized.append(ev_copy)
    return sanitized, sorted(list(masked))

def canonicalize_for_hash(obj: Any) -> str:
    def _clean(x):
        if isinstance(x, dict):
            return {k: _clean(v) for k, v in sorted(x.items()) if v is not None and v != ""}
        if isinstance(x, list):
            return [_clean(i) for i in x]
        return x
    cleaned = _clean(obj)
    return json.dumps(cleaned, sort_keys=True, ensure_ascii=False, separators=(",", ":"))

def compute_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def generate_stable_flow_id(flow_name: str, canonical_json: str, shorten: int = 8) -> str:
    if flow_name:
        h = compute_sha256(canonical_json)
        return f"flow::{flow_name}::{h[:shorten]}"
    return f"flow::unnamed::{uuid.uuid4().hex[:shorten]}"

def build_metadata(source_type: str,
                   origin: str,
                   flow_name: str = None,
                   user: str = None,
                   jira_id: str = None,
                   project: str = None,
                   hash_val: str = None,
                   masked_selectors: List[str] = None,
                   version: int = 1,
                   notes: str = None) -> Dict:
    meta = {
        "id": None,
        "source_type": source_type,
        "origin": origin,
        "jira_id": jira_id,
        "project": project,
        "flow_name": flow_name,
        "user": user,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "hash": hash_val,
        "redaction": bool(masked_selectors),
        "sensitive_fields_masked": masked_selectors or [],
        "version": version,
        "notes": notes or ""
    }
    return meta

def prepare_artifact_and_metadata_for_ingest(raw_events: List[Dict],
                                             source_type: str = "workflow_recorder",
                                             origin: str = "streamlit_user",
                                             flow_name: str = None,
                                             user: str = None,
                                             jira_id: str = None,
                                             project: str = None,
                                             custom_sensitive: Set[str] = None,
                                             version: int = 1,
                                             notes: str = None) -> Tuple[Dict, Dict, str]:
    sanitized_events, masked = sanitize_events(raw_events, custom_sensitive=custom_sensitive)
    artifact = {
        "flow_name": flow_name,
        "steps": sanitized_events,
        "url": None,
        "meta": {"recorded_by": user}
    }
    canonical_json = canonicalize_for_hash(artifact)
    h = compute_sha256(canonical_json)
    doc_id = generate_stable_flow_id(flow_name or "unnamed", canonical_json)
    metadata = build_metadata(
        source_type=source_type,
        origin=origin,
        flow_name=flow_name,
        user=user,
        jira_id=jira_id,
        project=project,
        hash_val=h,
        masked_selectors=masked,
        version=version,
        notes=notes
    )
    metadata["id"] = doc_id
    return artifact, metadata, doc_id
