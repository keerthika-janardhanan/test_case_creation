"""
Ingest a refined recorder JSON (.refined.json) into the vector DB as per-step documents.

Usage (Windows PowerShell):
  python -m app.ingest_refined_flow --file "app\\generated_flows\\<your>.refined.json" --flow-name "Create Supplier"

This will:
- Parse the refined JSON { pages, elements, steps }
- Drop noisy rows like action == 'Type' or CSS-only artifacts
- Create one Chroma document per step with stable metadata:
    artifact_type=test_case, source=recorder_refined, flow_name, flow_hash, step_index, action, page_heading, heading
- Content kept concise (~500-1000 chars) for effective retrieval
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

try:
    from .vector_db import VectorDBClient  # type: ignore
    from .ingest_utils import ingest_artifact  # type: ignore
    from .hashstore import compute_hash  # type: ignore
except ImportError:
    from app.vector_db import VectorDBClient
    from ingest_utils import ingest_artifact
    from hashstore import compute_hash


def _slugify(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", (text or "").lower()).strip("-") or "scenario"


def _looks_like_css_noise(text: str) -> bool:
    if not text:
        return False
    s = str(text).strip()
    # Patterns like '#_FOpt1\:_FOr1:...' or '::content'
    if s.startswith('#') and ('\\:' in s or '::content' in s):
        return True
    # Very long token-like selectors
    if s.startswith('#') and len(s) > 40 and re.fullmatch(r"[#._a-zA-Z0-9\\:]+", s):
        return True
    return False


def _shorten(value: str, limit: int = 800) -> str:
    v = (value or "").strip()
    return v if len(v) <= limit else v[:limit] + "..."


def ingest_refined_file(file_path: str, flow_name: str | None = None) -> dict:
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"Refined JSON not found: {file_path}")
    data = json.loads(p.read_text(encoding="utf-8"))
    steps = data.get("steps") or []
    elements = data.get("elements") or []
    pages = data.get("pages") or []
    flow_name = flow_name or data.get("flow_name") or p.stem
    flow_slug = _slugify(flow_name)

    # Build a map of useful element info keyed by xpath/title/label for quick lookup
    el_index = {}
    for e in elements:
        key = (e.get("xpath") or e.get("title") or e.get("label") or "").strip()
        if key:
            el_index[key] = e

    flow_hash = compute_hash(json.dumps(steps, ensure_ascii=False))[:12]
    source_type = "recorder_refined"
    vdb = VectorDBClient(path=os.getenv("VECTOR_DB_PATH", "./vector_store"))

    try:
        vdb.collection.delete(where={"flow_slug": flow_slug, "type": source_type})
    except Exception:
        pass

    added = 0
    element_added = 0
    skipped = 0
    for idx, step in enumerate(steps, start=1):
        action = str(step.get("action") or "").strip()
        navigation = str(step.get("navigation") or "").strip()
        data_val = str(step.get("data") or "").strip()
        expected = str(step.get("expected") or "").strip()

        # Filter out noisy rows: action == 'Type' and CSS-only noise navigation
        if action.lower() == "type" and (_looks_like_css_noise(navigation) or not navigation):
            skipped += 1
            continue

        loc = step.get("locators") if isinstance(step, dict) else {}
        page_heading = str((loc or {}).get("page_heading") or "").strip()
        heading = str((loc or {}).get("heading") or "").strip()
        xpath = str((loc or {}).get("raw_xpath") or (loc or {}).get("xpath") or "").strip()
        title = str((loc or {}).get("title") or "").strip()
        labels = str((loc or {}).get("labels") or "").strip()

        # Attach a small element summary if we can resolve it
        el_key = xpath or title or labels
        el_info = el_index.get(el_key, {})

        content_payload = {
            "flow": flow_name,
            "flow_slug": flow_slug,
            "flow_hash": flow_hash,
            "step_index": idx,
            "action": action,
            "navigation": navigation,
            "data": data_val,
            "expected": expected,
            "page_heading": page_heading,
            "heading": heading,
            "xpath": xpath,
            "title": title,
            "labels": labels,
            "locators": step.get("locators"),
            "element": el_info,
        }

        # Keep content concise for retrieval while storing structured payload
        content_str = _shorten(
            f"{flow_name} | Step {idx}: {action}\nNavigation: {navigation}\nData: {data_val}\nExpected: {expected}\n"
            f"Page Heading: {page_heading} | Heading: {heading}\nXPath: {xpath} | Title/Label: {title or labels}"
        )

        metadata = {
            "artifact_type": "test_case",
            "type": "recorder_refined",
            "record_kind": "step",
            "flow_name": flow_name,
            "flow_slug": flow_slug,
            "flow_hash": flow_hash,
            "step_index": idx,
            "action": action,
            "navigation": navigation[:400],
            "data": data_val[:400],
            "expected": expected[:400],
            "page_heading": page_heading,
            "heading": heading,
        }

        # Stable id per flow slug + step index
        doc_id = f"{flow_slug}-s{idx:03}"
        # Use the generic helper to perform idempotent add (hashstore-backed)
        ingest_artifact(
            source_type,
            {
                "summary": content_str,
                "payload": content_payload,
            },
            metadata,
            provided_id=doc_id,
        )
        added += 1

    for element_idx, element in enumerate(elements, start=1):
        label = (element.get("label") or element.get("name") or element.get("title") or "").strip()
        if not label:
            continue
        role = str(element.get("role") or "").strip()
        tag = str(element.get("tag") or "").strip()
        locators = {}
        if role and label:
            locators = {"byRole": {"role": role, "name": label}}
        elif label:
            locators = {"byText": label}
        payload = {
            "flow": flow_name,
            "flow_slug": flow_slug,
            "flow_hash": flow_hash,
            "element_index": element_idx,
            "label": label,
            "role": role,
            "tag": tag,
            "name": element.get("name") or "",
            "title": element.get("title") or "",
            "locators": {"playwright": locators} if locators else {},
        }
        metadata = {
            "artifact_type": "test_case",
            "type": "recorder_refined",
            "record_kind": "element",
            "flow_name": flow_name,
            "flow_slug": flow_slug,
            "flow_hash": flow_hash,
            "element_index": element_idx,
            "label": label,
            "role": role,
            "tag": tag,
        }
        doc_id = f"{flow_slug}-e{element_idx:03}"
        ingest_artifact(
            source_type,
            {
                "summary": f"{flow_name} | Element {element_idx}: {label} ({role or tag})",
                "payload": payload,
            },
            metadata,
            provided_id=doc_id,
        )
        element_added += 1

    return {
        "added": added,
        "elements": element_added,
        "skipped": skipped,
        "flow_name": flow_name,
        "flow_hash": flow_hash,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest refined recorder JSON into vector DB (per-step)")
    parser.add_argument("--file", required=True, help="Path to *.refined.json")
    parser.add_argument("--flow-name", default=None, help="Override flow name (optional)")
    args = parser.parse_args(argv)

    stats = ingest_refined_file(args.file, args.flow_name)
    print(json.dumps({"status": "ok", **stats}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
