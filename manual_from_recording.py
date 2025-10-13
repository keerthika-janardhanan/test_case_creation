#!/usr/bin/env python3
"""Convert a Playwright recording or trace to manual test cases aligned with an Excel template."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from zipfile import ZipFile

import pandas as pd

try:
    from bs4 import BeautifulSoup  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    BeautifulSoup = None  # type: ignore


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class Action:
    index: int
    kind: str
    selector: Optional[str] = None
    value: Optional[str] = None
    url: Optional[str] = None
    expect_target: Optional[str] = None
    expect_type: Optional[str] = None
    expect_value: Optional[str] = None
    raw: str = ""
    metadata: Dict[str, object] = field(default_factory=dict)


@dataclass
class EnrichedAction:
    action_id: str
    index: int
    kind: str
    primary_locator: str
    fallback_locators: List[str]
    human_name: str
    ui_block_title: str
    navigation_text: str
    data_text: str
    expected_text: str
    category: str
    locators_summary: str
    element_attributes: Dict[str, object]
    test_data: Dict[str, str]
    screenshot_path: str
    dom_snippet: str
    raw_value: Optional[str]
    metadata: Dict[str, object] = field(default_factory=dict)


@dataclass
class ManualStep:
    test_id: str
    title: str
    preconditions: str
    step_number: int
    category: str
    navigation: str
    data: str
    expected: str
    test_data_summary: str
    locators_summary: str
    link_action_ids: List[str]
    type: str = "positive"
    priority: str = "Medium"
    assumptions: str = ""


# ---------------------------------------------------------------------------
# Constants & heuristics
# ---------------------------------------------------------------------------


CATEGORY_KEYWORDS: List[Tuple[str, str]] = [
    ("sign in", "Log into Oracle"),
    ("login", "Log into Oracle"),
    ("log into oracle", "Log into Oracle"),
    ("navigator", "Navigate"),
    ("procurement", "Navigate"),
    ("supplier", "Create a Supplier"),
    ("create supplier", "Create a Supplier"),
    ("address", "Addresses"),
    ("transaction tax", "Transaction Tax"),
    ("tax", "Transaction Tax"),
    ("site", "Sites"),
    ("contact", "Contacts"),
    ("save and close", "End of Task"),
    ("end of task", "End of Task"),
]

ENRICHMENT_COLUMNS = [
    "Test ID",
    "Action ID",
    "Action Kind",
    "Primary Locator",
    "Fallback Locators",
    "Element Human Name",
    "UI Block Title",
    "Element Attributes JSON",
    "Screenshot Path",
    "DOM Snippet",
]

STRING_QUOTE_RE = re.compile(r"^([\"'])(.*)\1$")
CSS_ATTR_RE = re.compile(r"\[([a-zA-Z0-9_\-:]+)(?:[~|^$*]?=)[\"']?([^\"'\]]+)")


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def strip_quotes(text: Optional[str]) -> str:
    if not text:
        return ""
    match = STRING_QUOTE_RE.match(text.strip())
    return match.group(2) if match else text.strip()


def mask_sensitive(value: Optional[str]) -> str:
    raw = strip_quotes(value)
    if not raw:
        return ""
    lowered = raw.lower()
    if any(key in lowered for key in ("password", "secret", "token", "passcode")):
        return "********"
    if "@" in raw and " " not in raw:
        return "<qa_user>"
    if len(raw) > 40:
        return raw[:8] + "..." + raw[-4:]
    return raw


def truncate(text: str, limit: int = 500) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def safe_join(items: Iterable[str], sep: str = "; ") -> str:
    filtered = [item.strip() for item in items if item and item.strip()]
    return sep.join(dict.fromkeys(filtered))  # dedupe while preserving order


def words_count(sentence: str) -> int:
    return len(sentence.strip().split())


def shorten_sentence(sentence: str, max_words: int = 25) -> str:
    words = sentence.strip().split()
    if len(words) <= max_words:
        return sentence.strip()
    return " ".join(words[:max_words]) + "..."


def load_dom_snapshots(dom_dir: Optional[str]) -> List[Dict[str, str]]:
    if not dom_dir:
        return []
    dom_path = Path(dom_dir)
    if not dom_path.exists():
        raise FileNotFoundError(f"DOM directory not found: {dom_dir}")
    html_files = sorted(dom_path.glob("*.html"))
    snapshots: List[Dict[str, str]] = []
    for html_file in html_files:
        try:
            html = html_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            html = html_file.read_text(encoding="latin-1", errors="ignore")
        snapshots.append({"path": str(html_file), "html": html})
    return snapshots


def find_heading_from_dom(html: str) -> str:
    if not BeautifulSoup:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag_name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
        heading = soup.find(tag_name)
        if heading and heading.get_text(strip=True):
            return heading.get_text(strip=True)
    heading = soup.find(attrs={"role": "heading"})
    if heading and heading.get_text(strip=True):
        return heading.get_text(strip=True)
    return ""


def best_effort_dom_snippet(selector: str, dom_snapshot: Optional[Dict[str, str]]) -> str:
    if not dom_snapshot or not dom_snapshot.get("html"):
        return ""
    html = dom_snapshot["html"]
    if selector:
        selector_key = strip_quotes(selector)
        idx = html.find(selector_key)
        if idx != -1:
            start = max(0, idx - 120)
            end = min(len(html), idx + 380)
            return truncate(html[start:end])
    return truncate(html[:500])


# ---------------------------------------------------------------------------
# Template reading
# ---------------------------------------------------------------------------


def read_template(path: str) -> Tuple[str, List[str], pd.DataFrame]:
    excel = pd.ExcelFile(path)
    sheet_name = excel.sheet_names[0]
    df = excel.parse(sheet_name=sheet_name, dtype=str)
    df = df.fillna("")
    columns = list(df.columns)
    return sheet_name, columns, df


# ---------------------------------------------------------------------------
# Recording parsing
# ---------------------------------------------------------------------------


def parse_recording(path: str) -> Tuple[List[Action], Dict[str, object]]:
    lower = path.lower()
    if lower.endswith((".ts", ".js")):
        return parse_codegen_file(path), {}
    if lower.endswith(".zip"):
        return parse_trace_zip(path)
    raise ValueError(f"Unsupported recording format: {path}")

def parse_codegen_file(path: str) -> List[Action]:
    text = Path(path).read_text(encoding="utf-8")
    actions: List[Tuple[int, Action]] = []

    patterns = [
        ("goto", re.compile(r"await\s+page\.goto\((?P<arg>[^)]+)\);", re.MULTILINE)),
        ("click", re.compile(r"await\s+(?P<selector>page\.[^;\n]+?)\.click\((?P<args>[^)]*)\);", re.MULTILINE)),
        ("fill", re.compile(r"await\s+(?P<selector>page\.[^;\n]+?)\.fill\((?P<value>[^)]*)\);", re.MULTILINE)),
        ("press", re.compile(r"await\s+(?P<selector>page\.[^;\n]+?)\.press\((?P<value>[^)]*)\);", re.MULTILINE)),
        ("check", re.compile(r"await\s+(?P<selector>page\.[^;\n]+?)\.check\((?P<args>[^)]*)\);", re.MULTILINE)),
        ("selectOption", re.compile(r"await\s+(?P<selector>page\.[^;\n]+?)\.selectOption\((?P<value>[^)]*)\);", re.MULTILINE)),
        ("expect", re.compile(
            r"await\s+expect\((?P<target>[^)]+)\)\.(?P<method>toHaveURL|toHaveText|toContainText|toBeVisible|toBeHidden|"
            r"toHaveAttribute|toHaveValue)\((?P<value>[^)]*)\);",
            re.MULTILINE,
        )),
    ]

    for kind, pattern in patterns:
        for match in pattern.finditer(text):
            start = match.start()
            if kind == "goto":
                url_literal = match.group("arg")
                actions.append(
                    (
                        start,
                        Action(
                            index=0,
                            kind="goto",
                            url=strip_quotes(url_literal),
                            raw=match.group(0).strip(),
                        ),
                    )
                )
            elif kind == "expect":
                actions.append(
                    (
                        start,
                        Action(
                            index=0,
                            kind="expect",
                            expect_target=match.group("target").strip(),
                            expect_type=match.group("method"),
                            expect_value=strip_quotes(match.group("value")),
                            raw=match.group(0).strip(),
                        ),
                    )
                )
            else:
                selector = match.group("selector").strip()
                value_group = match.groupdict().get("value") or match.groupdict().get("args") or ""
                actions.append(
                    (
                        start,
                        Action(
                            index=0,
                            kind=kind.lower(),
                            selector=selector,
                            value=strip_quotes(value_group),
                            raw=match.group(0).strip(),
                        ),
                    )
                )

    actions.sort(key=lambda item: item[0])
    ordered: List[Action] = []
    for idx, (_, action) in enumerate(actions, start=1):
        action.index = idx
        ordered.append(action)
    return ordered


def parse_trace_zip(path: str) -> Tuple[List[Action], Dict[str, object]]:
    actions: List[Action] = []
    tmp_dir = tempfile.mkdtemp(prefix="trace_extract_")
    meta: Dict[str, object] = {"extraction_dir": tmp_dir}

    with ZipFile(path) as archive:
        trace_files = [name for name in archive.namelist() if name.endswith(".trace")]
        for trace_file in trace_files:
            with archive.open(trace_file) as handle:
                for line in handle:
                    try:
                        event = json.loads(line.decode("utf-8"))
                    except json.JSONDecodeError:
                        continue
                    if event.get("type") != "action":
                        continue
                    metadata = event.get("metadata", {})
                    action_type = metadata.get("type") or metadata.get("action")
                    selector = metadata.get("selector")
                    url = metadata.get("url") or metadata.get("navigatedTo")
                    value = metadata.get("value") or metadata.get("text")
                    attachments = metadata.get("attachments", [])
                    saved_attachments = []
                    for attachment in attachments or []:
                        path_in_zip = attachment.get("path")
                        if not path_in_zip or path_in_zip not in archive.namelist():
                            continue
                        filename = Path(path_in_zip).name
                        target = Path(tmp_dir) / filename
                        with open(target, "wb") as out_file:
                            out_file.write(archive.read(path_in_zip))
                        saved_attachments.append(
                            {
                                "name": attachment.get("name"),
                                "path": str(target),
                                "contentType": attachment.get("contentType"),
                            }
                        )
                    metadata["attachments"] = saved_attachments
                    if not action_type:
                        continue
                    kind = action_type.lower()
                    if kind == "assert" and metadata.get("apiName"):
                        kind = "expect"
                    action = Action(
                        index=len(actions) + 1,
                        kind=kind,
                        selector=selector,
                        value=value,
                        url=url,
                        raw=json.dumps(metadata),
                        metadata=metadata,
                    )
                    if kind == "expect":
                        action.expect_target = metadata.get("selector") or metadata.get("target")
                        action.expect_type = metadata.get("apiName")
                        action.expect_value = metadata.get("value") or metadata.get("text")
                    actions.append(action)

    for idx, action in enumerate(actions, start=1):
        action.index = idx
    return actions, meta


# ---------------------------------------------------------------------------
# Locator analysis
# ---------------------------------------------------------------------------


def analyze_locator(selector: Optional[str]) -> Dict[str, object]:
    info: Dict[str, object] = {
        "primary": strip_quotes(selector) if selector else "",
        "role": "",
        "name": "",
        "label": "",
        "placeholder": "",
        "text": "",
        "data_attrs": {},
        "id": "",
        "tag": "",
        "fallback": [],
        "human": "",
    }
    if not selector:
        return info
    expr = selector
    role_match = re.search(r"getByRole\(\s*['\"]([^'\"]+)['\"]", expr)
    if role_match:
        info["role"] = role_match.group(1)
        name_match = re.search(r"name\s*:\s*['\"]([^'\"]+)['\"]", expr)
        if name_match:
            info["name"] = name_match.group(1)
            info["human"] = name_match.group(1)
            info["fallback"].append(f"role={info['role']} name='{info['name']}'")
        else:
            info["fallback"].append(f"role={info['role']}")

    label_match = re.search(r"getByLabel\(\s*['\"]([^'\"]+)['\"]", expr)
    if label_match:
        info["label"] = label_match.group(1)
        if not info["human"]:
            info["human"] = info["label"]
        info["fallback"].append(f"label='{info['label']}'")

    placeholder_match = re.search(r"getByPlaceholder\(\s*['\"]([^'\"]+)['\"]", expr)
    if placeholder_match:
        info["placeholder"] = placeholder_match.group(1)
        if not info["human"]:
            info["human"] = info["placeholder"]
        info["fallback"].append(f"placeholder='{info['placeholder']}'")

    text_match = re.search(r"getByText\(\s*['\"]([^'\"]+)['\"]", expr)
    if text_match:
        info["text"] = text_match.group(1)
        if not info["human"]:
            info["human"] = info["text"]
        info["fallback"].append(f"text='{info['text']}'")

    data_attrs = {}
    for attr, value in CSS_ATTR_RE.findall(expr):
        if attr.lower() in ("data-testid", "data-test", "data-qa", "data-test-id"):
            data_attrs[attr] = value
            info["fallback"].append(f"{attr}={value}")
        elif attr.lower() == "id":
            info["id"] = value
            info["fallback"].append(f"id='{value}'")
    if data_attrs:
        info["data_attrs"] = data_attrs

    tag_match = re.search(r"locator\(\s*['\"]([a-zA-Z][a-zA-Z0-9_-]*)", expr)
    if tag_match:
        info["tag"] = tag_match.group(1)

    if not info["human"]:
        if info["label"]:
            info["human"] = info["label"]
        elif info["name"]:
            info["human"] = info["name"]
        elif info["text"]:
            info["human"] = info["text"]

    info["primary"] = expr.strip()
    return info


def derive_category(text: str, default: str = "Navigate") -> str:
    candidate = text.lower()
    for keyword, label in CATEGORY_KEYWORDS:
        if keyword in candidate:
            return label
    return default


def build_locator_summary(primary: str, fallbacks: List[str]) -> str:
    if fallbacks:
        return f"Primary: {primary}; Fallback: {safe_join(fallbacks)}"
    return f"Primary: {primary}"


# ---------------------------------------------------------------------------
# Action enrichment
# ---------------------------------------------------------------------------


def enrich_action(
    action: Action,
    action_id: str,
    dom_snapshot: Optional[Dict[str, str]],
) -> EnrichedAction:
    selector_info = analyze_locator(action.selector)
    primary_locator = selector_info.get("primary") or (action.url or action.raw or "")
    fallback_locators = selector_info.get("fallback", [])
    human_name = selector_info.get("human") or ""
    ui_block_title = ""
    if dom_snapshot:
        ui_block_title = find_heading_from_dom(dom_snapshot.get("html", ""))

    element_attrs: Dict[str, object] = {
        "role": selector_info.get("role") or None,
        "name": selector_info.get("name") or None,
        "label": selector_info.get("label") or None,
        "placeholder": selector_info.get("placeholder") or None,
        "text": selector_info.get("text") or None,
        "data_attrs": selector_info.get("data_attrs") or {},
        "id": selector_info.get("id") or None,
        "tag": selector_info.get("tag") or None,
    }

    navigation_text = ""
    data_text = ""
    expected_text = ""
    test_data: Dict[str, str] = {}
    raw_value = action.value

    if action.kind == "goto":
        url = action.url or ""
        navigation_text = f"Navigate to {url}"
        expected_text = f"Page loads at {url}"
        human_name = human_name or "Start page"
        category = derive_category(url or "navigate", "Navigate")
    elif action.kind == "click":
        label = human_name or selector_info.get("text") or "target control"
        navigation_text = f"Click {label}"
        expected_text = f"{label} responds and the target view appears."
        category = derive_category(label)
    elif action.kind == "fill":
        label = human_name or selector_info.get("label") or "field"
        masked_value = mask_sensitive(action.value)
        navigation_text = f"Type {masked_value} into {label}"
        data_text = f"{label}: {masked_value}"
        expected_text = f"{label} stores the entered value."
        test_data[label] = masked_value
        category = derive_category(label)
    elif action.kind == "press":
        label = human_name or selector_info.get("label") or "field"
        key = mask_sensitive(action.value)
        navigation_text = f"Press {key} in {label}"
        expected_text = f"{label} accepts the key input."
        category = derive_category(label)
    elif action.kind in ("selectoption", "select_option"):
        label = human_name or selector_info.get("label") or "dropdown"
        selection = mask_sensitive(action.value)
        navigation_text = f"Select {selection} in {label}"
        data_text = f"{label}: {selection}"
        expected_text = f"{label} shows {selection} as selected."
        test_data[label] = selection
        category = derive_category(label)
    elif action.kind in ("check", "uncheck"):
        label = human_name or selector_info.get("label") or "checkbox"
        navigation_text = f"{action.kind.capitalize()} {label}"
        expected_text = f"{label} is {'checked' if action.kind == 'check' else 'cleared'}."
        category = derive_category(label)
    elif action.kind == "expect":
        expectation = build_expectation_text(action)
        navigation_text = ""
        expected_text = expectation
        category = derive_category(expectation or "assert", "Verification")
    else:
        navigation_text = action.raw or action.kind.capitalize()
        expected_text = "Action completes successfully."
        category = derive_category(navigation_text)

    navigation_text = shorten_sentence(navigation_text)
    data_text = shorten_sentence(data_text) if data_text else ""
    expected_text = shorten_sentence(expected_text) if expected_text else "UI reflects the action outcome."

    screenshot_path = ""
    dom_snippet = best_effort_dom_snippet(primary_locator, dom_snapshot)

    attachments = action.metadata.get("attachments") if action.metadata else None
    if attachments:
        for att in attachments:  # type: ignore[assignment]
            if not isinstance(att, dict):
                continue
            ctype = (att.get("contentType") or "").lower()
            path_value = att.get("path") or att.get("path_in_zip") or att.get("resolvedPath")
            if not path_value and att.get("path"):
                path_value = att.get("path")
            if ctype.startswith("image/") and not screenshot_path and path_value:
                screenshot_path = str(path_value)
            if ctype.startswith("text/html") and not dom_snippet and path_value:
                try:
                    html_text = Path(path_value).read_text(encoding="utf-8")
                except Exception:
                    html_text = ""
                dom_snippet = truncate(html_text)

    locators_summary = build_locator_summary(str(primary_locator), fallback_locators)

    return EnrichedAction(
        action_id=action_id,
        index=action.index,
        kind=action.kind,
        primary_locator=str(primary_locator),
        fallback_locators=fallback_locators,
        human_name=human_name,
        ui_block_title=ui_block_title,
        navigation_text=navigation_text,
        data_text=data_text,
        expected_text=expected_text,
        category=category,
        locators_summary=locators_summary,
        element_attributes={k: v for k, v in element_attrs.items() if v not in (None, "", {}, [])},
        test_data=test_data,
        screenshot_path=screenshot_path,
        dom_snippet=dom_snippet,
        raw_value=raw_value,
        metadata=action.metadata or {},
    )


def build_expectation_text(action: Action) -> str:
    method = (action.expect_type or "").lower()
    target = action.expect_target or "element"
    value = action.expect_value or ""
    if method.endswith("tobevisible"):
        return f"{target} is visible."
    if method.endswith("tobehidden"):
        return f"{target} becomes hidden."
    if method.endswith("tohaveurl"):
        return f"URL updates to {value}."
    if method.endswith("tohavetext") or method.endswith("tocontaintext"):
        return f"{target} displays text '{value}'."
    if method.endswith("tohaveattribute"):
        return f"{target} shows attribute value '{value}'."
    if method.endswith("tohavevalue"):
        return f"{target} retains value '{value}'."
    return "Verification passes."


# ---------------------------------------------------------------------------
# Manual step grouping
# ---------------------------------------------------------------------------


def derive_title(enriched_actions: List[EnrichedAction], recording_path: str) -> str:
    base = Path(recording_path).stem.replace("_", " ").title()
    return f"Manual validation for {base}"


def derive_preconditions(enriched_actions: List[EnrichedAction]) -> str:
    url = ""
    for action in enriched_actions:
        if action.kind == "goto" and action.navigation_text:
            url = strip_quotes(action.navigation_text.replace("Navigate to", "").strip())
            break
    hints = [
        "Oracle Fusion environment reachable",
        "Valid procurement user credentials available",
    ]
    if url:
        hints.insert(0, f"Target URL known: {url}")
    return "; ".join(dict.fromkeys(hints))


def aggregate_test_data(enriched_actions: List[EnrichedAction]) -> Dict[str, str]:
    aggregated: Dict[str, str] = {}
    for action in enriched_actions:
        aggregated.update(action.test_data)
    return aggregated


def format_test_data_summary(data: Dict[str, str]) -> str:
    if not data:
        return ""
    lines = [f"{key}: {value}" for key, value in data.items()]
    return "\n".join(lines)


def group_actions(
    enriched_actions: List[EnrichedAction],
    recording_path: str,
) -> List[ManualStep]:
    if not enriched_actions:
        return []

    test_id = "TC-001"
    title = derive_title(enriched_actions, recording_path)
    preconditions = derive_preconditions(enriched_actions)
    aggregated_data = aggregate_test_data(enriched_actions)
    aggregated_data_summary = format_test_data_summary(aggregated_data)

    steps: List[ManualStep] = []
    last_step: Optional[ManualStep] = None

    for action in enriched_actions:
        if action.kind == "expect" and last_step:
            expectation = action.expected_text
            joined_expected = f"{last_step.expected} {expectation}".strip()
            last_step.expected = shorten_sentence(joined_expected)
            last_step.link_action_ids.append(action.action_id)
            continue

        navigation_text = action.navigation_text or action.primary_locator
        if not navigation_text:
            navigation_text = action.kind.capitalize()

        step = ManualStep(
            test_id=test_id,
            title=title if not steps else "",
            preconditions=preconditions if not steps else "",
            step_number=len(steps) + 1,
            category=action.category,
            navigation=navigation_text,
            data=action.data_text,
            expected=action.expected_text,
            test_data_summary=aggregated_data_summary if not steps else "",
            locators_summary=action.locators_summary,
            link_action_ids=[action.action_id],
            assumptions="",
        )
        steps.append(step)
        last_step = step

    if steps:
        steps[0].assumptions = "Derived from Playwright recording."
    return steps


# ---------------------------------------------------------------------------
# Mapping to template rows
# ---------------------------------------------------------------------------


def map_step_to_row(
    step: ManualStep,
    columns: List[str],
    previous_category: Optional[str],
) -> Dict[str, object]:
    row: Dict[str, object] = {column: "" for column in columns}
    category_shown = step.category if step.category != (previous_category or "") else ""
    locator_summary = step.locators_summary

    numbered_instruction = f"{step.step_number}. {step.navigation}"

    for column in columns:
        normalized = column.strip().lower()
        if normalized in {"sl", "step", "step no", "#"}:
            row[column] = step.step_number
        elif normalized == "action":
            row[column] = category_shown
        elif "navigation" in normalized or normalized == "step description":
            row[column] = step.navigation
        elif "steps" == normalized:
            row[column] = numbered_instruction
        elif "key data" in normalized or "data element" in normalized:
            row[column] = step.data
        elif "test data" in normalized:
            row[column] = step.test_data_summary or step.data
        elif "expected" in normalized:
            row[column] = step.expected
        elif "precondition" in normalized:
            row[column] = step.preconditions
        elif "title" in normalized:
            row[column] = step.title
        elif normalized in {"test id", "id"} or "test id" in normalized:
            row[column] = step.test_id
        elif "type" in normalized:
            row[column] = step.type
        elif "priority" in normalized:
            row[column] = step.priority
        elif "assumption" in normalized or "note" in normalized:
            row[column] = step.assumptions if step.assumptions else locator_summary
        elif "locator" in normalized or "reference" in normalized:
            row[column] = locator_summary
        elif "action ids" in normalized or "link" in normalized:
            row[column] = ", ".join(step.link_action_ids)

    return row


def build_main_rows(steps: List[ManualStep], columns: List[str]) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    previous_category: Optional[str] = None
    for step in steps:
        row = map_step_to_row(step, columns, previous_category)
        rows.append(row)
        if step.category:
            previous_category = step.category
    return rows


def build_enrichment_rows(
    enriched_actions: List[EnrichedAction],
    test_id: str,
) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for action in enriched_actions:
        fallback_str = safe_join(action.fallback_locators)
        element_json = json.dumps(action.element_attributes, ensure_ascii=False)
        rows.append(
            {
                "Test ID": test_id,
                "Action ID": action.action_id,
                "Action Kind": action.kind,
                "Primary Locator": action.primary_locator,
                "Fallback Locators": fallback_str,
                "Element Human Name": action.human_name,
                "UI Block Title": action.ui_block_title,
                "Element Attributes JSON": element_json,
                "Screenshot Path": action.screenshot_path,
                "DOM Snippet": truncate(action.dom_snippet, 500),
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Workbook writing
# ---------------------------------------------------------------------------


def write_workbook(
    template_path: str,
    sheet_name: str,
    columns: List[str],
    step_rows: List[Dict[str, object]],
    enrichment_rows: List[Dict[str, object]],
    out_path: str,
) -> None:
    df_main = pd.DataFrame(step_rows, columns=columns)
    df_enrichment = pd.DataFrame(enrichment_rows, columns=ENRICHMENT_COLUMNS)

    with pd.ExcelWriter(out_path, engine="xlsxwriter") as writer:
        df_main.to_excel(writer, sheet_name=sheet_name, index=False)
        df_enrichment.to_excel(writer, sheet_name="Enrichment", index=False)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description="Convert Playwright recording or trace into manual test cases aligned with a template.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--template", required=True, help="Path to oracle_template.xlsx")
    parser.add_argument("--recording", required=True, help="Path to Playwright codegen .ts/.js or trace.zip")
    parser.add_argument("--dom", required=False, help="Optional directory containing HTML snapshots")
    parser.add_argument("--out", required=False, default="manual_from_recording.xlsx", help="Destination Excel path")

    args = parser.parse_args(argv)

    sheet_name, columns, _ = read_template(args.template)

    actions, meta = parse_recording(args.recording)
    if not actions:
        raise RuntimeError("No actions parsed from recording.")

    dom_snapshots = load_dom_snapshots(args.dom)
    dom_iter = iter(dom_snapshots) if dom_snapshots else None

    enriched_actions: List[EnrichedAction] = []
    for idx, action in enumerate(actions, start=1):
        action_id = f"A-{idx}"
        dom_snapshot = next(dom_iter, None) if dom_iter else None
        enriched = enrich_action(action, action_id, dom_snapshot)
        enriched_actions.append(enriched)

    manual_steps = group_actions(enriched_actions, args.recording)
    if not manual_steps:
        raise RuntimeError("Failed to produce manual steps from actions.")

    main_rows = build_main_rows(manual_steps, columns)
    enrichment_rows = build_enrichment_rows(enriched_actions, manual_steps[0].test_id if manual_steps else "TC-001")

    write_workbook(
        template_path=args.template,
        sheet_name=sheet_name,
        columns=columns,
        step_rows=main_rows,
        enrichment_rows=enrichment_rows,
        out_path=args.out,
    )

    actions_count = len(actions)
    step_count = len(manual_steps)
    print(f"Parsed {actions_count} actions and generated {step_count} manual steps.")
    print(f"Output written to {args.out}")

    extraction_dir = meta.get("extraction_dir")
    if extraction_dir:
        try:
            shutil.rmtree(str(extraction_dir))
        except Exception:
            pass


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover - top-level guard
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

