from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    from .recorder_enricher import GENERATED_DIR, slugify, _describe_step  # type: ignore
except ImportError:  # pragma: no cover - allow running as script
    from recorder_enricher import GENERATED_DIR, slugify, _describe_step  # type: ignore

REFINED_VERSION = "2025.10"


def _first_non_empty(*values: Optional[Any]) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, Iterable) and not isinstance(value, (str, bytes, dict)):
            text = ", ".join(str(item) for item in value if item)
            if text.strip():
                return text.strip()
    return ""


def _normalise_playwright_selector(selector: Any, element: Dict[str, Any]) -> str:
    if isinstance(selector, str) and selector.strip():
        return selector.strip()
    if isinstance(selector, dict):
        by_role = selector.get("byRole")
        if isinstance(by_role, dict):
            role = by_role.get("role")
            name = by_role.get("name")
            if role and name:
                return f'getByRole("{role}", name="{name}")'
        by_label = selector.get("byLabel")
        if by_label:
            return f'getByLabel("{by_label}")'
        by_text = selector.get("byText")
        if by_text:
            return f'getByText("{by_text}")'
    stable = element.get("stableSelector")
    if stable:
        return str(stable)
    css_path = element.get("cssPath")
    if css_path:
        return str(css_path)
    xpath = element.get("xpath")
    if xpath:
        return str(xpath)
    return ""


def _collect_xpath_candidates(*values: Optional[str]) -> List[str]:
    seen: List[str] = []
    for raw in values:
        if not raw:
            continue
        candidate = str(raw)
        if candidate and candidate not in seen:
            seen.append(candidate)
    return seen


def _compose_locators(action: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    selectors = action.get("selectorStrategies") or {}
    element = action.get("element") or {}

    playwright_selector = selectors.get("aria") or selectors.get("playwright") or element.get("playwright")
    playwright_str = _normalise_playwright_selector(playwright_selector, element)
    css = selectors.get("css") or element.get("cssPath") or ""
    xpath = selectors.get("xpath") or ""
    element_xpath = element.get("xpath") or ""
    labels_raw = element.get("labels")
    if isinstance(labels_raw, (list, tuple, set)):
        labels = ", ".join(str(label) for label in labels_raw if label)
    else:
        labels = str(labels_raw or "")
    heading = _first_non_empty(element.get("nearestHeading"), element.get("heading"))
    page_heading = _first_non_empty(element.get("pageHeading"), element.get("page_heading"))

    locators: Dict[str, Any] = {
        "playwright": playwright_str,
        "stable": element.get("stableSelector") or css or element_xpath or xpath or "",
        "xpath": xpath,
        "xpath_candidates": _collect_xpath_candidates(xpath, element_xpath),
        "raw_xpath": element_xpath or xpath,
        "css": css,
        "title": element.get("title") or "",
        "labels": labels,
        "role": element.get("role") or "",
        "name": _first_non_empty(element.get("name"), element.get("ariaLabel")),
        "tag": element.get("tag") or "",
        "heading": heading,
        "page_heading": page_heading,
    }

    element_label = _first_non_empty(labels, locators["name"], locators["title"], locators["tag"])
    return locators, element_label


def _convert_action(action: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    action_type = (action.get("type") or action.get("action") or "").lower()
    extra = action.get("extra") or {}
    selectors = action.get("selectorStrategies") or {}

    mapped_action = None
    value = None

    if action_type == "change":
        mapped_action = "fill"
        value = extra.get("valueMasked") or extra.get("value") or ""
    elif action_type == "click":
        mapped_action = "click"
        value = ""
    elif action_type == "press":
        key = extra.get("key") or extra.get("code")
        if not key:
            return None
        mapped_action = "press"
        value = str(key)
    else:
        return None

    locators, element_label = _compose_locators(action)
    selector = (
        selectors.get("aria")
        or selectors.get("playwright")
        or locators.get("stable")
    )
    if not selector:
        selector = locators.get("css") or locators.get("raw_xpath") or ""

    if not selector:
        return None

    notes = action.get("notes") or []
    description = "; ".join(n for n in notes if n)

    raw_step = {
        "action": mapped_action,
        "selector": selector,
        "value": str(value or ""),
        "url": action.get("pageUrl"),
        "description": description,
    }

    element_entry = {
        "tag": locators.get("tag", ""),
        "title": locators.get("title", ""),
        "label": element_label,
        "role": locators.get("role", ""),
        "name": locators.get("name", "") or element_label,
        "xpath": locators.get("raw_xpath", "") or locators.get("xpath", ""),
        "css": locators.get("css", ""),
        "heading": locators.get("heading", ""),
        "page_heading": locators.get("page_heading", ""),
    }

    data_label = element_label or locators.get("tag", "") or "Field"

    return {
        "raw": raw_step,
        "locators": locators,
        "element": element_entry,
        "data_label": data_label,
        "value": str(value or ""),
        "metadata": {
            "actionId": action.get("actionId"),
            "type": action_type,
        },
    }


def build_refined_flow_from_metadata(
    metadata: Dict[str, Any],
    flow_name: Optional[str] = None,
) -> Dict[str, Any]:
    actions = metadata.get("actions") or []
    if not actions:
        raise ValueError("Recorder metadata does not contain any actions.")

    resolved_flow_name = flow_name or metadata.get("flowName") or metadata.get("flow_name") or "Recorder Flow"

    converted: List[Dict[str, Any]] = []
    for action in actions:
        entry = _convert_action(action)
        if entry:
            converted.append(entry)

    if not converted:
        # Check if there were degraded actions that couldn't be converted
        degraded_count = sum(1 for a in actions if a.get("degraded"))
        if degraded_count > 0:
            raise ValueError(
                f"No valid recorder actions found. {degraded_count} action(s) were degraded with incomplete selectors. "
                "Please perform meaningful interactions in the browser (fill forms, click buttons with proper selectors) and try again."
            )
        else:
            raise ValueError(
                "No recorder actions could be converted into refined steps. "
                "Please perform some interactions in the browser before stopping the recording."
            )

    elements_map: Dict[Tuple[str, str, str, str, str], Dict[str, Any]] = {}
    for entry in converted:
        element = entry["element"]
        key = (
            element.get("xpath", "") or "",
            element.get("css", "") or "",
            element.get("label", "") or "",
            element.get("name", "") or "",
            element.get("tag", "") or "",
        )
        if key not in elements_map:
            elements_map[key] = element

    refined_steps: List[Dict[str, Any]] = []
    previous_section = ""
    last_url = None
    for idx, entry in enumerate(converted, start=1):
        raw_step = entry["raw"]
        enriched = _describe_step(resolved_flow_name, raw_step, last_url, previous_section)
        previous_section = enriched["section"]
        if raw_step.get("action") == "goto" and raw_step.get("url"):
            last_url = raw_step.get("url")

        data_field = ""
        if raw_step.get("action") == "fill":
            value = entry["value"]
            if value:
                label = entry["data_label"]
                data_field = f"{label}: {value}" if label else value

        refined_steps.append(
            {
                "step": idx,
                "action": raw_step["action"].capitalize(),
                "navigation": enriched["navigation"],
                "data": data_field,
                "expected": enriched["expected"],
                "locators": entry["locators"],
            }
        )

    refined_flow = {
        "refinedVersion": REFINED_VERSION,
        "flow_name": resolved_flow_name,
        "flow_id": metadata.get("flowId"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pages": [
            {
                "pageId": page.get("pageId"),
                "pageUrl": page.get("pageUrl"),
                "pageTitle": page.get("pageTitle"),
                "mainHeading": page.get("mainHeading"),
            }
            for page in (metadata.get("pages") or [])
        ],
        "elements": list(elements_map.values()),
        "steps": refined_steps,
    }
    return refined_flow


def auto_refine_and_ingest(
    session_dir: str | Path,
    metadata: Dict[str, Any],
    *,
    flow_name: Optional[str] = None,
    ingest: bool = True,
) -> Dict[str, Any]:
    session_path = Path(session_dir)
    refined_flow = build_refined_flow_from_metadata(metadata, flow_name=flow_name)

    resolved_flow_name = refined_flow["flow_name"]
    slug = slugify(resolved_flow_name)
    session_suffix = session_path.name or metadata.get("flowId") or "session"
    output_path = GENERATED_DIR / f"{slug}-{session_suffix}.refined.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(refined_flow, fh, indent=2, ensure_ascii=False)

    ingest_stats: Optional[Dict[str, Any]] = None
    ingest_error: Optional[str] = None
    if ingest:
        try:
            from .ingest_refined_flow import ingest_refined_file  # type: ignore
        except ImportError:  # pragma: no cover - fallback for direct execution
            from ingest_refined_flow import ingest_refined_file  # type: ignore
        
        try:
            ingest_stats = ingest_refined_file(str(output_path), resolved_flow_name)
        except Exception as e:
            ingest_error = f"Vector DB ingestion failed: {str(e)}"
            print(f"[WARNING] {ingest_error}")

    return {
        "refined_path": str(output_path),
        "flow_name": resolved_flow_name,
        "ingested": bool(ingest_stats),
        "ingest_stats": ingest_stats,
        "ingest_error": ingest_error,
    }
