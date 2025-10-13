import json
import math
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd


GENERATED_DIR = Path("app/generated_flows")
GENERATED_DIR.mkdir(exist_ok=True, parents=True)

ROLE_PATTERN = re.compile(r"getByRole\(\s*['\"]([^'\"]+)['\"]")
NAME_PATTERN = re.compile(r"name\s*:\s*['\"]([^'\"]+)['\"]")
LABEL_PATTERN = re.compile(r"getByLabel\(\s*['\"]([^'\"]+)['\"]")
TEXT_PATTERN = re.compile(r"getByText\(\s*['\"]([^'\"]+)['\"]")
PLACEHOLDER_PATTERN = re.compile(r"getByPlaceholder\(\s*['\"]([^'\"]+)['\"]")
LOCATOR_TEXT_PATTERN = re.compile(r"text=([^\"'\)]+)")
DATA_TESTID_PATTERN = re.compile(r"data-testid['\"]?\s*[:=]\s*['\"]([^'\"]+)['\"]")


@dataclass
class TargetMetadata:
    human_name: Optional[str] = None
    role: Optional[str] = None
    text: Optional[str] = None
    label: Optional[str] = None
    title: Optional[str] = None
    placeholder: Optional[str] = None
    aria_label: Optional[str] = None
    data_testid: Optional[str] = None
    css: Optional[str] = None
    xpath: Optional[str] = None
    all_selectors: Optional[List[str]] = None
    parent: Optional[Dict[str, Optional[str]]] = None
    siblings: Optional[List[Dict[str, Optional[str]]]] = None
    ancestors: Optional[List[Dict[str, Optional[str]]]] = None
    position: Optional[Dict[str, Optional[object]]] = None
    stability_score: float = 0.5
    selector_strategy: Optional[str] = None
    healing_hints: Optional[List[Dict[str, str]]] = None


@dataclass
class EnrichedStep:
    sl: int
    action: str
    navigation: str
    data_examples: str
    expected: str
    step_kind: str
    page_url: Optional[str]
    frame: Dict[str, Optional[object]]
    targets: List[TargetMetadata]
    data_inputs: Dict[str, str]
    assertions: List[Dict[str, object]]
    timings: Dict[str, Optional[int]]


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", name.lower()).strip("-")
    return slug or "scenario"


def _extract_role_name(selector: str) -> Tuple[Optional[str], Optional[str]]:
    role_match = ROLE_PATTERN.search(selector or "")
    name_match = NAME_PATTERN.search(selector or "")
    return (
        role_match.group(1) if role_match else None,
        name_match.group(1) if name_match else None,
    )


def _extract_label(selector: str) -> Optional[str]:
    match = LABEL_PATTERN.search(selector or "")
    return match.group(1) if match else None


def _extract_text(selector: str) -> Optional[str]:
    match = TEXT_PATTERN.search(selector or "")
    if match:
        return match.group(1)
    match = LOCATOR_TEXT_PATTERN.search(selector or "")
    return match.group(1) if match else None


def _extract_placeholder(selector: str) -> Optional[str]:
    match = PLACEHOLDER_PATTERN.search(selector or "")
    return match.group(1) if match else None


def _extract_data_testid(selector: str) -> Optional[str]:
    match = DATA_TESTID_PATTERN.search(selector or "")
    return match.group(1) if match else None


def _clean_selector(selector: str) -> str:
    if not selector:
        return ""
    cleaned = selector.replace("await ", "").replace("page.", "")
    cleaned = cleaned.replace("locator(", "").replace(")", "")
    return cleaned.strip()


def _role_to_phrase(role: Optional[str]) -> str:
    mapping = {
        "link": "link",
        "button": "button",
        "tab": "tab",
        "menuitem": "menu item",
        "checkbox": "checkbox",
        "combobox": "drop-down",
        "textbox": "field",
    }
    return mapping.get(role, role or "element")


def _mask_secret(field_name: str, value: str) -> str:
    if not value:
        return value
    lower = field_name.lower()
    if any(keyword in lower for keyword in ["password", "passcode", "secret", "token"]):
        return "***redacted***"
    return value


def _selector_strategy(metadata: TargetMetadata) -> str:
    strategies = []
    if metadata.role and (metadata.text or metadata.label or metadata.human_name):
        strategies.append("role")
    if metadata.data_testid:
        strategies.append("data-testid")
    if metadata.css:
        strategies.append("css")
    if metadata.text:
        strategies.append("text")
    if metadata.xpath:
        strategies.append("xpath")
    return ">".join(strategies) if strategies else "xpath"


def _stability_score(metadata: TargetMetadata) -> float:
    score = 0.4
    if metadata.role and (metadata.text or metadata.label):
        score += 0.3
    if metadata.data_testid:
        score += 0.2
    if metadata.css:
        score += 0.1
    return min(score, 0.95)


def _healing_hints(metadata: TargetMetadata) -> List[Dict[str, str]]:
    hints: List[Dict[str, str]] = []
    if metadata.role and metadata.text:
        hints.append({"if": "role/name changes", "use": f"text={metadata.text}"})
    if metadata.data_testid:
        hints.append({"if": "role/name missing", "use": f"data-testid={metadata.data_testid}"})
    if metadata.css:
        hints.append({"if": "primary selector fails", "use": metadata.css})
    if metadata.xpath:
        hints.append({"if": "other attributes missing", "use": metadata.xpath})
    return hints


def _quadrant_hint(position: Optional[Dict[str, Optional[object]]]) -> Optional[str]:
    if not position:
        return None
    viewport = position.get("viewport")
    if not viewport:
        return None
    x = position.get("x")
    y = position.get("y")
    if x is None or y is None:
        return None
    width, height = viewport
    horizontal = "left" if x < width / 2 else "right"
    vertical = "top" if y < height / 2 else "bottom"
    return f"{vertical}-{horizontal}"


def _action_section(identifier: str, previous: str, default: str) -> str:
    lowered = identifier.lower()
    for keyword, label in [
        ("login", "Log into Oracle"),
        ("sign in", "Log into Oracle"),
        ("navigate", "Navigate"),
        ("supplier", "Create a Supplier"),
        ("address", "Addresses"),
        ("transaction", "Transaction Tax"),
        ("site", "Sites"),
        ("contact", "Contacts"),
        ("end", "End of Task"),
    ]:
        if keyword in lowered:
            return label
    return previous or default


def _step_kind(action_raw: str) -> str:
    mapping = {
        "goto": "navigate",
        "click": "click",
        "fill": "fill",
        "type": "fill",
        "select_option": "select",
        "select": "select",
        "check": "check",
        "uncheck": "uncheck",
        "hover": "hover",
        "press": "press",
    }
    return mapping.get(action_raw.lower(), "interact")


def _expected_from_navigation(navigation: str, default: str) -> str:
    lower = navigation.lower()
    for keyword, expectation in [
        ("navigator", "Navigator opened."),
        ("task pane", "Task Pane is displayed."),
        ("create supplier", "The Create Supplier pop up window is visible."),
        ("addresses", "The Addresses tab is displayed."),
        ("transaction tax", "The Transaction Tax work area is displayed."),
        ("receiving", "Receiving sub tab is displayed."),
        ("purchasing", "Purchasing sub tab is displayed."),
        ("invoicing", "Invoicing sub tab is displayed."),
        ("save and close", "Confirmation dialog is displayed."),
        ("sign in", "Login submitted."),
    ]:
        if keyword in lower:
            return expectation
    return default or "Action completes successfully."


def enrich_recorder_flow(flow_name: str, flow_steps: List[Dict[str, object]]) -> Tuple[List[Dict[str, str]], List[Dict[str, object]]]:
    table_rows: List[Dict[str, str]] = []
    sidecar: List[Dict[str, object]] = []
    last_url: Optional[str] = None
    sl_counter = 1
    previous_action_label = ""

    for raw_step in flow_steps:
        action_raw = str(raw_step.get("action") or "").lower()

        if action_raw == "goto":
            last_url = raw_step.get("url") or last_url

        enriched = _describe_step(flow_name, raw_step, last_url, previous_action_label)
        section_label = enriched["section"]
        navigation_text = enriched["navigation"]
        expected_text = enriched["expected"]
        data_examples = enriched["data_examples"]
        targets = enriched["targets"]

        row = {
            "sl": str(sl_counter) if section_label != previous_action_label else "",
            "Action": section_label,
            "Navigation Steps": navigation_text,
            "Key Data Element Examples": data_examples,
            "Expected Results": expected_text,
        }
        table_rows.append(row)

        sidecar_entry = {
            "sl": sl_counter if section_label != previous_action_label else len(sidecar) + 1,
            "action": section_label,
            "step_kind": enriched["step_kind"],
            "page_url": last_url,
            "frame": {"name": None, "url": None, "index": 0},
            "targets": [asdict(target) for target in targets],
            "data_inputs": enriched["data_inputs"],
            "expected": expected_text,
            "assertions": [],
            "timings": {"start_ms": None, "end_ms": None, "think_time_ms": None},
        }
        sidecar.append(sidecar_entry)

        if section_label != previous_action_label:
            sl_counter += 1

        previous_action_label = section_label

    return table_rows, sidecar


def _describe_step(flow_name: str, step: Dict[str, object], previous_url: Optional[str], previous_section: str) -> Dict[str, object]:
    action_raw = str(step.get("action") or "").lower()
    selector: Optional[str] = step.get("selector")  # type: ignore
    value: str = step.get("value") or ""
    description: str = step.get("description") or ""

    role, name = _extract_role_name(selector or "")
    label = _extract_label(selector or "")
    text_value = _extract_text(selector or "")
    placeholder = _extract_placeholder(selector or "")
    data_testid = _extract_data_testid(selector or "")

    human_name = name or label or text_value or placeholder or data_testid or "element"
    role_phrase = _role_to_phrase(role)
    action_hint = ""
    navigation_text = ""
    data_examples = ""

    step_kind = _step_kind(action_raw)
    expected_text = ""

    if action_raw in {"goto", "navigate"}:
        navigation_text = f"Navigate to {step.get('url')}"
        expected_text = "Target page is displayed."
        action_hint = "navigate"
    elif action_raw in {"click", "press"}:
        navigation_text = f"Click the {human_name} {role_phrase}".strip()
        expected_text = _expected_from_navigation(navigation_text, "Element responds as expected.")
        action_hint = "click"
    elif action_raw in {"fill", "type"}:
        navigation_text = f"Enter {human_name}"
        data_examples = f"{human_name}: {_mask_secret(human_name, value or '<value>')}"
        expected_text = "Field captures the entered data."
        action_hint = "enter data"
    elif action_raw in {"select", "select_option"}:
        navigation_text = f"Choose {value or 'an option'} in {human_name}"
        data_examples = f"{human_name}: {value or '<option>'}"
        expected_text = "Option is selected."
        action_hint = "select"
    elif action_raw in {"check", "uncheck"}:
        navigation_text = f"{action_raw.capitalize()} {human_name}"
        expected_text = "Checkbox state updates."
        action_hint = "toggle"
    else:
        navigation_text = description or f"Interact with {human_name}"
        expected_text = "Action completes successfully."
        action_hint = action_raw or "interact"

    section_label = _action_section(navigation_text or action_hint, previous_section, flow_name)

    target_metadata = TargetMetadata(
        human_name=human_name,
        role=role,
        text=text_value,
        label=label,
        placeholder=placeholder,
        aria_label=label or name,
        data_testid=data_testid,
        css=None,
        xpath=None,
        all_selectors=list(filter(None, [selector])),
        parent=None,
        siblings=None,
        ancestors=None,
        position=None,
    )
    target_metadata.selector_strategy = _selector_strategy(target_metadata)
    target_metadata.stability_score = _stability_score(target_metadata)
    target_metadata.healing_hints = _healing_hints(target_metadata)

    data_inputs = {}
    if data_examples:
        key, _, val = data_examples.partition(":")
        data_inputs[key.strip()] = val.strip()

    navigation_text = navigation_text + _selector_hint_suffix(navigation_text, target_metadata)
    expected_text = _expected_from_navigation(navigation_text, expected_text)

    return {
        "section": section_label,
        "navigation": navigation_text,
        "expected": expected_text,
        "data_examples": data_examples,
        "targets": [target_metadata],
        "step_kind": step_kind,
        "data_inputs": data_inputs,
    }


def _selector_hint_suffix(navigation: str, metadata: TargetMetadata) -> str:
    hint = _quadrant_hint(metadata.position)
    if hint and hint not in navigation:
        return f" ({hint.replace('-', ' ')})"
    return ""


def persist_enriched_artifacts(flow_name: str, table_rows: List[Dict[str, str]], sidecar: List[Dict[str, object]], create_xlsx: bool = True) -> Dict[str, str]:
    slug = slugify(flow_name)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    cache_key = f"{slug}_{timestamp}"
    output_dir = GENERATED_DIR / slug
    output_dir.mkdir(parents=True, exist_ok=True)

    csv_path = output_dir / f"{cache_key}.csv"
    json_path = output_dir / f"{cache_key}.json"
    df = pd.DataFrame(table_rows, columns=["sl", "Action", "Navigation Steps", "Key Data Element Examples", "Expected Results"])
    df.to_csv(csv_path, index=False)

    xlsx_path = None
    if create_xlsx:
        xlsx_path = output_dir / f"{cache_key}.xlsx"
        with pd.ExcelWriter(xlsx_path, engine="xlsxwriter") as writer:
            df.to_excel(writer, index=False, sheet_name="Scenario")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(sidecar, f, indent=2, ensure_ascii=False)

    return {
        "cache_key": cache_key,
        "csv_path": str(csv_path),
        "xlsx_path": str(xlsx_path) if xlsx_path else "",
        "json_path": str(json_path),
        "step_count": str(len(table_rows)),
    }
