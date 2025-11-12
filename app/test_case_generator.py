import os
import json
import re
import ast
import copy
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import pandas as pd
from app.vector_db import VectorDBClient
from langchain_openai import AzureChatOpenAI
from app.recorder_enricher import slugify, GENERATED_DIR
try:
    from .ingest_refined_flow import ingest_refined_file  # type: ignore
except ImportError:
    from ingest_refined_flow import ingest_refined_file

# Section inference keywords -> section titles
SECTION_KEYWORDS = [
    ("login", "Log into Oracle"),
    ("sign in", "Log into Oracle"),
    ("navigator", "Navigate"),
    ("navigate", "Navigate"),
    ("supplier", "Create Supplier"),
    ("addresses", "Addresses"),
    ("sites", "Sites"),
    ("contacts", "Contacts"),
    ("transaction tax", "Transaction Tax"),
]

# Minimal selector/locator helpers used in this module
ROLE_PATTERN = re.compile(r"getByRole\(\s*['\"]([^'\"]+)['\"]")
NAME_PATTERN = re.compile(r"name\s*:\s*['\"]([^'\"]+)['\"]")
LABEL_PATTERN = re.compile(r"getByLabel\(\s*['\"]([^'\"]+)['\"]")
TEXT_PATTERN = re.compile(r"getByText\(\s*['\"]([^'\"]+)['\"]")
PLACEHOLDER_PATTERN = re.compile(r"placeholder\s*=\s*['\"]([^'\"]+)['\"]")
LOCATOR_TEXT_PATTERN = re.compile(r"text\s*=\s*['\"]([^'\"]+)['\"]")

SELECTOR_HINTS = {}
EXPECTED_HINTS = {}

logger = logging.getLogger(__name__)

class TestCaseGenerator:
    def __init__(self, db: Optional[VectorDBClient] = None, llm: Optional[AzureChatOpenAI] = None, template: Optional[dict] = None):
        self.db = db or VectorDBClient()
        self.template = template or {}
        self.relevant_types = {
            "ui_flow",
            "test_case",
            "testcase",
            "playwright",
            "script",
            "script_scaffold",
            "repo_scaffold",
            "locators",
            "locator",
            "page_object",
            "pages",
            "bdd",
            "jira",
            "document",
            "website_doc",
            "requirement",
            "spec",
            "test_plan",
        }
        self.default_fields = [
            "id",
            "title",
            "type",
            "preconditions",
            "steps",
            "data",
            "expected",
            "priority",
            "tags",
            "assumptions",
        ]
        self.cached_flow_steps: List[dict] = []
        # LLM client (Azure OpenAI)
        self.llm = llm or AzureChatOpenAI(
            openai_api_version=os.getenv("OPENAI_API_VERSION"),
            azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT", "GPT-4o"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_key=os.getenv("AZURE_OPENAI_KEY"),
            temperature=0.2,
        )

    def generate_test_cases(self, story: str, per_step_negatives: int = 1, per_step_edges: int = 1, max_steps_for_variants: int = 8, llm_only: bool = False):
        try:
            context_chunks, raw_flow_steps, context_sources = self._collect_context(story)
        except re.error as exc:
            pattern = getattr(exc, "pattern", None)
            raise ValueError(
                f"Regex failure while collecting context (pattern={pattern!r}): {exc}"
            ) from exc
        flow_steps = self._normalize_flow_steps(raw_flow_steps)
        self.cached_flow_steps = flow_steps
        context_text = "\n\n---\n".join(context_chunks) if context_chunks else "(No direct context retrieved. Provide best-effort scenarios and state assumptions.)"

        # Agentic path: attempt LLM with retries; if recorder flow missing and LLM fails, synthesize from vector context
        cases = self._agentic_generate(story, context_text, flow_steps, context_sources, llm_only=llm_only)
        # Ensure granular coverage: add per-step negative/edge variants when missing
        cases = self._ensure_per_step_variants(
            cases,
            flow_steps,
            per_step_negatives=per_step_negatives,
            per_step_edges=per_step_edges,
            max_steps=max_steps_for_variants,
            story=story,
        )
        if not llm_only:
            cases = self._humanize_cases(cases)
            cases = self._ensure_steps_alignment(cases)
        return cases

    @staticmethod
    def _normalize_story_title(story: str) -> str:
        if not story:
            return ""
        text = str(story).strip()
        if not text:
            return ""
        # Remove common suffixes like "- Positive Flow", "Positive Scenario", etc.
        patterns = [
            r"[\-\u2013\u2014]\s*(positive|negative|edge)\s+(flow|scenario)\b.*$",
            r"\b(positive|negative|edge)\s+(flow|scenario)\b.*$",
            r"[\-\u2013\u2014]\s*(happy|main|primary)\s+path\b.*$",
        ]
        cleaned = text
        for pattern in patterns:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip()
        # Drop leftover trailing separators
        cleaned = re.sub(r"[\-\u2013\u2014\s_]+$", "", cleaned).strip()
        return cleaned or text

    def _normalize_flow_steps(self, flow_steps: Optional[List[dict]]) -> List[dict]:
        if not flow_steps:
            return []

        normalized: List[dict] = []
        for idx, raw in enumerate(flow_steps, start=1):
            if not isinstance(raw, dict):
                continue
            step_index = raw.get("step") or raw.get("step_index") or idx
            try:
                step_index = int(step_index)
            except (TypeError, ValueError):
                step_index = idx

            locators = self._sanitize_locators(raw.get("locators"))
            element_block = raw.get("element")
            if not isinstance(element_block, dict):
                element_block = {}

            action = str(raw.get("action") or element_block.get("label") or "").strip()
            navigation = str(raw.get("navigation") or "").strip()
            data_value = str(raw.get("data") or "").strip()
            expected_value = str(raw.get("expected") or "").strip()
            label = self._derive_label(locators, raw, element_block)
            role = str(
                locators.get("role")
                or element_block.get("role")
                or raw.get("role")
                or ""
            ).strip()
            locator_hint = self._derive_locator_hint(locators)

            normalized.append(
                {
                    "step": step_index,
                    "action": action,
                    "navigation": navigation,
                    "data": data_value,
                    "expected": expected_value,
                    "label": label,
                    "role": role,
                    "locator": locator_hint,
                    "locators": locators,
                    "record_kind": str(raw.get("record_kind") or ""),
                }
            )

        normalized.sort(key=lambda item: item.get("step", 0))
        return normalized

    def _sanitize_locators(self, locators) -> dict:
        if not isinstance(locators, dict):
            return {}

        allowed_keys = {
            "playwright",
            "stable",
            "css",
            "labels",
            "label",
            "name",
            "role",
            "tag",
            "heading",
            "page_heading",
            "title",
        }
        sanitized: dict = {}

        for key, value in locators.items():
            key_text = str(key)
            key_lower = key_text.lower()
            if "xpath" in key_lower:
                continue

            if isinstance(value, str):
                trimmed = value.strip()
                if trimmed.startswith("/html"):
                    continue
                if key_lower in allowed_keys:
                    sanitized[key_text] = trimmed
                elif key_lower == "css":
                    sanitized[key_text] = trimmed
                continue

            if isinstance(value, (int, float, bool)) and key_lower in allowed_keys:
                sanitized[key_text] = value
                continue

            if isinstance(value, dict):
                nested = self._sanitize_locators(value)
                if nested and (key_lower in allowed_keys or nested):
                    sanitized[key_text] = nested
                continue

            if isinstance(value, list):
                filtered_list = []
                for item in value:
                    if isinstance(item, str) and item.strip().startswith("/html"):
                        continue
                    if isinstance(item, dict):
                        nested_item = self._sanitize_locators(item)
                        if nested_item:
                            filtered_list.append(nested_item)
                    else:
                        filtered_list.append(item)
                if filtered_list and (key_lower in allowed_keys or filtered_list):
                    sanitized[key_text] = filtered_list
                continue

            if key_lower in allowed_keys:
                sanitized[key_text] = value

        return sanitized

    def _derive_label(self, locators: dict, raw_step: dict, element_block: dict) -> str:
        candidates: List[str] = []

        def _collect(value):
            if not value:
                return
            if isinstance(value, (list, tuple, set)):
                for part in value:
                    _collect(part)
                return
            if isinstance(value, dict):
                return
            text = str(value).strip()
            if text:
                candidates.append(text)

        if isinstance(locators, dict):
            _collect(locators.get("labels") or locators.get("label"))
            _collect(locators.get("name"))
        _collect(element_block.get("label"))
        _collect(element_block.get("name"))
        _collect(raw_step.get("label"))

        if not candidates:
            for fallback in (raw_step.get("navigation"), raw_step.get("action")):
                text = str(fallback or "").strip()
                if text:
                    candidates.append(text)
                    break

        if not candidates:
            return ""

        primary = candidates[0]
        primary = primary.split("|", 1)[0].strip()
        return primary.rstrip(":").strip()

    def _derive_locator_hint(self, locators: dict) -> str:
        if not isinstance(locators, dict):
            return ""

        candidate = locators.get("playwright") or locators.get("stable") or ""
        if isinstance(candidate, str):
            return candidate.strip()
        if isinstance(candidate, dict):
            by_role = candidate.get("byRole")
            if isinstance(by_role, dict):
                role = by_role.get("role")
                name = by_role.get("name")
                if role and name:
                    return f"byRole(role={role}, name={name})"
            try:
                return json.dumps(candidate, ensure_ascii=False)
            except TypeError:
                return str(candidate)
        return ""

    def _chunk_flow_steps(self, steps: List[dict], chunk_size: int = 8, overlap: int = 1) -> List[dict]:
        if not steps:
            return []

        if chunk_size <= 0:
            chunk_size = 8
        if overlap >= chunk_size:
            overlap = max(0, chunk_size - 1)

        ordered = sorted(steps, key=lambda item: item.get("step", 0))
        stride = chunk_size - overlap
        stride = stride if stride > 0 else chunk_size

        chunks: List[dict] = []
        for start in range(0, len(ordered), stride):
            subset = ordered[start : start + chunk_size]
            if not subset:
                continue
            chunks.append(
                {
                    "start": subset[0]["step"],
                    "end": subset[-1]["step"],
                    "steps": subset,
                }
            )
            if start + chunk_size >= len(ordered):
                break
        return chunks

    def _sanitize_llm_response(self, response) -> str:
        output = response.content if hasattr(response, "content") else str(response)
        try:
            output = re.sub(r"^```(?:json)?\s*", "", output, flags=re.DOTALL)
            output = re.sub(r"\s*```$", "", output, flags=re.DOTALL)
        except re.error as exc:
            pattern = getattr(exc, "pattern", None)
            raise ValueError(
                f"Regex failure while sanitising LLM output (pattern={pattern!r}): {exc}"
            ) from exc
        return output.strip()

    def _invoke_llm_json(self, prompt: str):
        resp = self.llm.invoke(prompt)
        output = self._sanitize_llm_response(resp)
        try:
            normalized = self._normalize_llm_json(output)
        except re.error as exc:
            pattern = getattr(exc, "pattern", None)
            raise ValueError(
                f"Regex failure while normalising LLM JSON (pattern={pattern!r}): {exc}"
            ) from exc

        try:
            return json.loads(normalized)
        except json.JSONDecodeError:
            repaired = self._repair_llm_output_to_json_array(normalized)
            if repaired is not None:
                return repaired
            raise

    def _generate_chunk_outline(
        self,
        story: str,
        chunk_payload: dict,
        chunk_index: int,
        total_chunks: int,
    ) -> List[dict]:
        steps = chunk_payload.get("steps") or []
        if not steps:
            return []
        payload = []
        for item in steps:
            payload.append(
                {
                    "step": item.get("step"),
                    "label": item.get("label"),
                    "action": item.get("action"),
                    "navigation": item.get("navigation"),
                    "data": item.get("data"),
                    "expected": item.get("expected"),
                    "role": item.get("role"),
                    "locator": item.get("locator"),
                }
            )

        prompt = self._build_chunk_prompt(story, payload, chunk_index, total_chunks)
        result = self._invoke_llm_json(prompt)
        if not isinstance(result, list):
            return []

        outline: List[dict] = []
        for item in result:
            if not isinstance(item, dict):
                continue
            step_no = item.get("step")
            if step_no is None:
                step_no = steps[0].get("step")
            try:
                step_no = int(step_no)
            except (TypeError, ValueError):
                step_no = steps[0].get("step")
            outline.append(
                {
                    "step": step_no,
                    "action": str(item.get("action") or "").strip(),
                    "navigation": str(item.get("navigation") or "").strip(),
                    "data": str(item.get("data") or "").strip(),
                    "expected": str(item.get("expected") or "").strip(),
                }
            )
        outline.sort(key=lambda entry: entry.get("step", 0))
        return outline

    def _build_chunk_prompt(
        self,
        story: str,
        payload: List[dict],
        chunk_index: int,
        total_chunks: int,
    ) -> str:
        payload_json = json.dumps(payload, ensure_ascii=False)
        return (
            "You are preparing manual QA step details for an Oracle Fusion workflow.\n"
            f"Flow identifier: '{story}'. This is chunk {chunk_index} of {total_chunks}.\n"
            "Each input object contains recorder metadata for a contiguous step range. "
            "Rewrite each item into a detailed manual step while preserving order and coverage.\n"
            "Rules:\n"
            "- Do not drop or merge steps.\n"
            "- Use imperative navigation phrasing grounded in labels.\n"
            "- Populate 'action', 'navigation', 'data', and 'expected'. Refer to recorder labels and actions.\n"
            "- If a field is missing, infer the minimal text ('data' may be empty).\n"
            "- Keep step numbers identical to input 'step'.\n"
            "- Output ONLY a JSON array (no prose, no code fences).\n\n"
            "Input JSON:\n"
            f"{payload_json}\n\n"
            "Return format example:\n"
            '[{"step": 1, "action": "...", "navigation": "...", "data": "...", "expected": "..."}]'
        )

    def _map_reduce_generate(
        self,
        story: str,
        context_text: str,
        flow_steps: List[dict],
        context_sources: List[str],
        max_attempts: int,
        llm_only: bool,
    ) -> List[dict]:
        chunks = self._chunk_flow_steps(flow_steps)
        if len(chunks) <= 1:
            return []

        positive_outline: List[dict] = []
        total_chunks = len(chunks)
        for idx, chunk in enumerate(chunks, start=1):
            try:
                outline_part = self._generate_chunk_outline(
                    story,
                    chunk,
                    idx,
                    total_chunks,
                )
            except Exception as exc:
                logger.debug("Chunk outline generation failed for chunk %s/%s: %s", idx, total_chunks, exc)
                return []
            if not outline_part:
                return []
            positive_outline.extend(outline_part)

        positive_outline.sort(key=lambda entry: entry.get("step", 0))
        outline_json = json.dumps(positive_outline, ensure_ascii=False)
        flow_steps_json = self._flow_steps_prompt_json(flow_steps)
        return self._single_pass_generate(
            story,
            context_text,
            flow_steps,
            context_sources,
            max_attempts=max_attempts,
            llm_only=llm_only,
            flow_steps_json_override=flow_steps_json,
            positive_outline_json=outline_json,
        )

    def _single_pass_generate(
        self,
        story: str,
        context_text: str,
        flow_steps: List[dict],
        context_sources: List[str],
        max_attempts: int = 2,
        llm_only: bool = False,
        flow_steps_json_override: Optional[str] = None,
        positive_outline_json: Optional[str] = None,
    ) -> List[dict]:
        flow_steps_prompt_json = flow_steps_json_override or self._flow_steps_prompt_json(flow_steps)
        for attempt in range(1, max_attempts + 1):
            prompt = self._build_generation_prompt(
                story,
                context_text,
                flow_steps_prompt_json,
                positive_outline_json=positive_outline_json,
            )
            if attempt > 1:
                strict_suffix = (
                    "\n\nIMPORTANT: Your previous output failed validation. Return ONLY a valid JSON array with objects "
                    f"containing keys {', '.join(self.default_fields)} and 'step_details'. No prose, no code fences, no trailing commas, no comments."
                )
                prompt = prompt + strict_suffix

            try:
                resp = self.llm.invoke(prompt)
            except re.error as exc:
                pattern = getattr(exc, "pattern", None)
                raise ValueError(
                    f"Regex failure while invoking LLM (pattern={pattern!r}): {exc}"
                ) from exc

            output = self._sanitize_llm_response(resp)

            try:
                normalized_output = self._normalize_llm_json(output)
            except re.error as exc:
                pattern = getattr(exc, "pattern", None)
                raise ValueError(
                    f"Regex failure while normalising LLM JSON (pattern={pattern!r}): {exc}"
                ) from exc

            parsed_cases = None
            try:
                parsed_cases = json.loads(normalized_output)
            except json.JSONDecodeError:
                repaired = self._repair_llm_output_to_json_array(normalized_output)
                if isinstance(repaired, list):
                    parsed_cases = repaired

            if isinstance(parsed_cases, list):
                cleaned = self._enforce_schema(parsed_cases)
                if not llm_only:
                    cleaned = self._inject_flow_details(cleaned, flow_steps, context_sources)
                if cleaned:
                    return cleaned

        if flow_steps and not llm_only:
            return self._fallback_from_flow(story, flow_steps)
        return self._synthesize_from_context(story, context_text, context_sources)

    def _humanize_cases(self, cases: List[dict]) -> List[dict]:
        if not cases:
            return cases

        payload: List[dict] = []
        original_steps_map: Dict[str, List[str]] = {}
        step_detail_lengths: Dict[str, int] = {}

        for case in cases:
            steps_field = case.get("steps")
            if isinstance(steps_field, list):
                step_lines = [str(item).strip() for item in steps_field if str(item).strip()]
            elif isinstance(steps_field, str):
                step_lines = [line.strip() for line in steps_field.split("\n") if line.strip()]
            else:
                step_lines = []

            detail_context = case.get("step_details")
            if not isinstance(detail_context, list):
                detail_context = []

            case_id = str(case.get("id") or "")
            if case_id:
                original_steps_map[case_id] = step_lines or []
                step_detail_lengths[case_id] = len(detail_context)

            payload.append(
                {
                    "id": case_id,
                    "type": str(case.get("type") or ""),
                    "steps": step_lines,
                    "step_details": detail_context,
                }
            )

        prompt = self._build_humanize_prompt(payload)
        if not prompt:
            return cases

        try:
            response = self._invoke_llm_json(prompt)
        except Exception as exc:
            logger.debug("Humanization prompt failed: %s", exc)
            return cases

        if not isinstance(response, list):
            return cases

        replacements: Dict[str, List[str]] = {}
        for item in response:
            if not isinstance(item, dict):
                continue
            case_id = str(item.get("id") or "").strip()
            steps_value = item.get("steps")
            if case_id and isinstance(steps_value, list):
                cleaned_steps = [str(step).strip() for step in steps_value if str(step).strip()]
                if cleaned_steps:
                    replacements[case_id] = cleaned_steps

        for case in cases:
            case_id = str(case.get("id") or "").strip()
            if not case_id:
                continue
            target_length = step_detail_lengths.get(case_id) or len(original_steps_map.get(case_id, []))
            candidate_steps = replacements.get(case_id)
            if candidate_steps and target_length and len(candidate_steps) == target_length:
                case["steps"] = replacements[case_id]
            elif candidate_steps and not target_length:
                case["steps"] = candidate_steps
            elif case_id in original_steps_map and original_steps_map[case_id]:
                case["steps"] = original_steps_map[case_id]

        return cases

    def _ensure_steps_alignment(self, cases: List[dict]) -> List[dict]:
        if not cases:
            return cases

        def _render_step(detail: dict) -> str:
            if not isinstance(detail, dict):
                return str(detail)
            action = str(detail.get("action") or "").strip()
            navigation = str(detail.get("navigation") or "").strip()
            data = str(detail.get("data") or "").strip()
            expected = str(detail.get("expected") or "").strip()
            parts = [p for p in [action, navigation] if p]
            if data:
                parts.append(f"Data: {data}")
            if expected:
                parts.append(f"Expected: {expected}")
            return " - ".join(parts) if parts else navigation or action or ""

        for case in cases:
            details = case.get("step_details")
            if not isinstance(details, list) or not details:
                continue
            expected_len = len(details)
            steps_field = case.get("steps")
            if isinstance(steps_field, list):
                current_steps = [str(step).strip() for step in steps_field if str(step).strip()]
            elif isinstance(steps_field, str):
                current_steps = [line.strip() for line in steps_field.split("\n") if line.strip()]
            else:
                current_steps = []
            if len(current_steps) != expected_len:
                case["steps"] = [_render_step(detail) for detail in details]
        return cases

    def _build_humanize_prompt(self, payload: List[dict]) -> str:
        if not payload:
            return ""
        payload_json = json.dumps(payload, ensure_ascii=False)
        return (
            "Refine manual QA step text so each instruction is a concise single sentence using imperative voice.\n"
            "Rules:\n"
            "- Preserve the number of steps and their order per case.\n"
            "- Include the UI control type when obvious (e.g., \"button\", \"link\", \"field\").\n"
            "- Mention example data values from 'step_details.data' inline (e.g., \"Enter 'TESTSR1' in Supplier\").\n"
            "- If a 'steps' array is empty, derive the wording from the provided 'step_details'.\n"
            "- Keep terminology aligned with Oracle Fusion UI labels, quoting the exact label text.\n"
            "- Do not introduce new steps or contradict the structured data.\n"
            "- Return ONLY a JSON array; each object must include 'id' and 'steps' (list of strings).\n\n"
            "Input JSON:\n"
            f"{payload_json}"
        )


    def _agentic_generate(self, story: str, context_text: str, flow_steps: List[dict], context_sources: List[str], max_attempts: int = 2, llm_only: bool = False) -> List[dict]:
        if flow_steps:
            try:
                chunked = self._map_reduce_generate(
                    story,
                    context_text,
                    flow_steps,
                    context_sources,
                    max_attempts=max_attempts,
                    llm_only=llm_only,
                )
                if chunked:
                    return chunked
            except Exception as exc:
                logger.debug("Chunked generation fallback triggered: %s", exc)

        return self._single_pass_generate(
            story,
            context_text,
            flow_steps,
            context_sources,
            max_attempts=max_attempts,
            llm_only=llm_only,
        )

    def _fallback_from_flow(self, story: str, flow_steps: List[dict]) -> List[dict]:
        step_details = [
            {
                "action": item.get("action", ""),
                "navigation": item.get("navigation", ""),
                "data": item.get("data", ""),
                "expected": item.get("expected", ""),
            }
            for item in flow_steps
        ]
        step_strings = []
        for detail in step_details:
            parts = [p for p in [detail.get("action", ""), detail.get("navigation", "")] if p]
            if detail.get("data"):
                parts.append(f"Data: {detail['data']}")
            if detail.get("expected"):
                parts.append(f"Expected: {detail['expected']}")
            step_strings.append(" - ".join(parts).strip(" -"))

        return [{
            "id": "TC001",
            "title": f"{story} - Positive Scenario".strip(" -"),
            "type": "positive",
            "preconditions": [],
            "step_details": step_details,
            "steps": step_strings,
            "data": {},
            "expected": step_details[-1].get("expected", ""),
            "priority": "medium",
            "tags": ["recorder", "auto-fallback"],
            "assumptions": [
                "Auto-generated directly from recorder flow steps due to empty LLM output. Please review wording."
            ],
        }]

    def _synthesize_from_context(self, story: str, context_text: str, context_sources: List[str]) -> List[dict]:
        # Heuristically extract procedural lines
        lines = [ln.strip() for ln in context_text.splitlines() if ln.strip()]
        keywords = ("click", "navigate", "select", "enter", "fill", "choose", "submit", "save", "open")
        step_lines: List[str] = []
        for ln in lines:
            low = ln.lower()
            if any(kw in low for kw in keywords):
                # Avoid the 'Source:' headers
                if not low.startswith("source:"):
                    step_lines.append(ln)
            if len(step_lines) >= 8:
                break

        step_details: List[dict] = []
        if step_lines:
            for idx, ln in enumerate(step_lines, start=1):
                step_details.append({
                    "action": "",
                    "navigation": ln,
                    "data": "",
                    "expected": "Action completes successfully.",
                })
        else:
            # Generic outline if no procedural text found
            step_details = [
                {"action": "Log into Oracle", "navigation": "Log into Oracle Fusion.", "data": "", "expected": "Home page is displayed."},
                {"action": "Navigate", "navigation": f"Navigate to the area relevant to '{story}'.", "data": "", "expected": "Target work area opens."},
                {"action": "Perform action", "navigation": f"Execute the core action for '{story}'.", "data": "", "expected": "System accepts inputs without errors."},
                {"action": "Verify", "navigation": "Confirm the business result is reflected (list/update/confirmation).", "data": "", "expected": "Outcome is visible and persisted."},
            ]

        steps = []
        for d in step_details:
            parts = [p for p in [d.get("action", ""), d.get("navigation", "")] if p]
            if d.get("data"):
                parts.append(f"Data: {d['data']}")
            if d.get("expected"):
                parts.append(f"Expected: {d['expected']}")
            steps.append(" - ".join(parts).strip(" -"))

        assumptions = []
        if context_sources:
            formatted = []
            for item in context_sources[:3]:
                if ":" in item:
                    src, desc = item.split(":", 1)
                    formatted.append(f"{src.strip()} -> {desc.strip()}")
                else:
                    formatted.append(item)
            assumptions.append("Derived from vector DB context: " + ", ".join(formatted))
        else:
            assumptions.append("Limited context available; outline inferred from story keywords.")

        return [{
            "id": "TC001",
            "title": f"{story} - Positive Scenario".strip(" -"),
            "type": "positive",
            "preconditions": [],
            "step_details": step_details,
            "steps": steps,
            "data": {},
            "expected": step_details[-1].get("expected", ""),
            "priority": "medium",
            "tags": ["vector-db", "agentic-fallback"],
            "assumptions": assumptions,
        }]

    # ----------------- JSON repair helpers -----------------
    def _repair_llm_output_to_json_array(self, text: str):
        """Best-effort extraction and repair of a JSON array from free-form LLM output.
        Returns a Python list on success, or None if irreparable.
        """
        if not text:
            return None

        s = text.strip()
        # Normalize smart quotes and BOM
        s = s.replace("\ufeff", "").replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")
        # Drop leading/trailing prose outside the first top-level JSON array using bracket scanning
        extracted = self._extract_first_json_array(s)
        candidate = (extracted or s).strip()
        # Remove trailing commas like {"a":1,}
        candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
        # If it looks like Python literals (single quotes), try ast.literal_eval
        def _try_parsers(payload: str):
            try:
                return json.loads(payload)
            except Exception:
                pass
            try:
                lit = ast.literal_eval(payload)
                if isinstance(lit, dict):
                    return [lit]
                if isinstance(lit, list):
                    return lit
            except Exception:
                pass
            return None

        parsed = _try_parsers(candidate)
        if isinstance(parsed, list):
            return parsed
        # Last resort 1: if the whole string is not parseable, try to find any bracketed list inside
        if extracted and extracted != candidate:
            parsed = _try_parsers(extracted)
            if isinstance(parsed, list):
                return parsed

        # Last resort 1b: attempt to auto-close unbalanced JSON and parse
        autoclose = self._auto_close_json(candidate)
        if autoclose:
            parsed = _try_parsers(autoclose)
            if isinstance(parsed, list):
                return parsed

        # Last resort 2: extract balanced JSON objects and return those that parse
        objects = self._extract_balanced_json_objects(s)
        parsed_objects = []
        for obj_str in objects:
            val = _try_parsers(obj_str)
            if isinstance(val, dict):
                parsed_objects.append(val)
        if parsed_objects:
            return parsed_objects

        return None

    def _extract_first_json_array(self, s: str) -> str | None:
        """Extract the first top-level JSON array substring using bracket depth accounting.
        Handles strings to avoid counting brackets inside quoted content.
        """
        start = s.find("[")
        if start == -1:
            return None
        i = start
        depth = 0
        in_str = False
        esc = False
        while i < len(s):
            ch = s[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == "[":
                    depth += 1
                elif ch == "]":
                    depth -= 1
                    if depth == 0:
                        return s[start : i + 1]
            i += 1
        return None

    def _extract_balanced_json_objects(self, s: str) -> List[str]:
        """Extract all balanced top-level JSON object substrings from text.
        This helps salvage partially valid content when the surrounding array is malformed or truncated.
        """
        results: List[str] = []
        depth = 0
        in_str = False
        esc = False
        start_idx: Optional[int] = None
        i = 0
        while i < len(s):
            ch = s[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == '{':
                    if depth == 0:
                        start_idx = i
                    depth += 1
                elif ch == '}':
                    if depth > 0:
                        depth -= 1
                        if depth == 0 and start_idx is not None:
                            results.append(s[start_idx:i+1])
                            start_idx = None
            i += 1
        return results

    def _auto_close_json(self, s: str) -> Optional[str]:
        """Attempt to auto-close unbalanced JSON strings and brackets.
        - Closes an open string if needed.
        - Appends missing closing braces/brackets.
        - Wraps top-level object in an array when appropriate.
        Returns a repaired string or None if no structure hints found.
        """
        if not s:
            return None
        text = s.strip()
        # Heuristic: if clearly not JSON-like, bail
        if not any(ch in text for ch in ['[', '{']):
            return None

        # If starts with object, consider wrapping later
        starts_with_object = text.lstrip().startswith('{') and not text.lstrip().startswith('[')

        stack: List[str] = []
        out_chars: List[str] = []
        in_str = False
        esc = False
        for ch in text:
            out_chars.append(ch)
            if in_str:
                if esc:
                    esc = False
                elif ch == '\\':
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            else:
                if ch == '"':
                    in_str = True
                elif ch == '{':
                    stack.append('}')
                elif ch == '[':
                    stack.append(']')
                elif ch == '}' or ch == ']':
                    if stack and stack[-1] == ch:
                        stack.pop()
                    else:
                        # unmatched closer; ignore
                        pass

        # Close open string
        if in_str:
            out_chars.append('"')

        # Append remaining closers in reverse order
        while stack:
            out_chars.append(stack.pop())

        repaired = ''.join(out_chars)

        # If started with an object and not already wrapped in an array, wrap
        if starts_with_object and not repaired.lstrip().startswith('['):
            repaired = f"[{repaired}]"

        return repaired

    def _fetch_supporting_artifacts(self, story: str, top_k: int) -> Tuple[List[str], List[str]]:
        chunks: List[str] = []
        context_sources: List[str] = []
        seen_ids: set[str] = set()
        queries = [story]
        tokens = [tok for tok in re.split(r"[^a-zA-Z0-9]+", story) if tok and len(tok) >= 3]
        for tok in tokens:
            if tok.lower() not in {q.lower() for q in queries}:
                queries.append(tok)

        for term in queries:
            if not term:
                continue
            try:
                results = self.db.query(term, top_k=top_k)
            except Exception as exc:
                logger.debug("Vector query failed for %s: %s", term, exc)
                continue

            for entry in results:
                is_dict = isinstance(entry, dict)
                entry_id = entry.get("id") if is_dict else str(entry)
                if entry_id in seen_ids:
                    continue
                seen_ids.add(entry_id)

                metadata = entry.get("metadata", {}) if is_dict else {}
                artifact_type = str(metadata.get("artifact_type") or metadata.get("type") or "").lower()
                if artifact_type == "recorder_refined":
                    continue
                if artifact_type and all(token not in artifact_type for token in self.relevant_types):
                    continue

                snippet = entry.get("content") if is_dict else str(entry)
                snippet = str(snippet)
                if len(snippet) > 1200:
                    snippet = snippet[:1200] + "..."

                descriptor = (
                    metadata.get("flow_name")
                    or metadata.get("title")
                    or metadata.get("file_path")
                    or metadata.get("component")
                    or (entry.get("id") if is_dict else None)
                )
                source_label = artifact_type or "unknown"
                descriptor_label = descriptor or entry_id
                chunks.append(f"Source: {source_label} | Descriptor: {descriptor_label}\n{snippet}")
                context_sources.append(f"{source_label}:{descriptor_label}")

                if len(chunks) >= top_k:
                    break

            if len(chunks) >= top_k:
                break

        return chunks, context_sources

    def _collect_context(self, story: str, top_k: int = 8) -> Tuple[List[str], List[dict], List[str]]:
        chunks: List[str] = []
        matched_flow_steps: List[dict] = []
        context_sources: List[str] = []

        vector_chunks, vector_steps = self._load_vector_flow(story)
        if not vector_steps and self._ensure_vector_flow_ingested(story):
            vector_chunks, vector_steps = self._load_vector_flow(story)

        if vector_steps:
            matched_flow_steps = vector_steps
            element_chunks, element_sources = self._build_recorder_element_chunks(vector_steps)
            if element_chunks:
                chunks.extend(element_chunks)
                context_sources.extend(element_sources[:top_k])
            else:
                chunks.extend(vector_chunks)
                for item in vector_steps[:3]:
                    descriptor = item.get("navigation") or item.get("action") or str(item.get("step"))
                    context_sources.append(f"recorder_refined:{descriptor}")
            return chunks, matched_flow_steps, context_sources

        support_chunks, support_sources = self._fetch_supporting_artifacts(story, top_k)
        chunks.extend(support_chunks)
        context_sources.extend(support_sources)

        flow_chunks, flow_steps = self._load_saved_flows(story)
        chunks.extend(flow_chunks)
        if flow_steps:
            matched_flow_steps = flow_steps
            for item in flow_steps[:3]:
                context_sources.append(f"recorder:{item.get('navigation') or item.get('action')}")

        if not matched_flow_steps:
            gen_chunks, gen_steps = self._load_refined_generated_flow(story)
            if gen_steps:
                matched_flow_steps = gen_steps
                element_chunks, element_sources = self._build_recorder_element_chunks(gen_steps)
                if element_chunks:
                    chunks.extend(element_chunks)
                    context_sources.extend(element_sources[:top_k])
                else:
                    chunks.extend(gen_chunks)
                    for item in gen_steps[:3]:
                        context_sources.append(f"refined:{item.get('navigation') or item.get('action')}")
            else:
                chunks.extend(gen_chunks)

        return chunks, matched_flow_steps, context_sources

    def _load_vector_flow(self, story: str, top_k: int = 256) -> Tuple[List[str], List[dict]]:
        normalized_story = self._normalize_story_title(story)
        flow_slug = slugify(normalized_story or story)
        steps_map: dict[int, dict] = {}
        element_map: dict[int, dict] = {}
        flow_hashes: set[str] = set()

        candidate_slugs_lower = set()
        metadata_slug_filters = set()
        candidate_names = set()
        original_story = str(story or "").strip()
        if flow_slug:
            candidate_slugs_lower.add(flow_slug.lower())
            metadata_slug_filters.add(flow_slug)
            if "-" in flow_slug:
                alt = flow_slug.replace("-", "_")
                candidate_slugs_lower.add(alt.lower())
                metadata_slug_filters.add(alt)
            if "_" in flow_slug:
                alt = flow_slug.replace("_", "-")
                candidate_slugs_lower.add(alt.lower())
                metadata_slug_filters.add(alt)
        story_clean = self._normalize_story_title(original_story) or original_story
        if story_clean:
            candidate_names.add(story_clean.lower())
        if original_story and original_story.lower() != story_clean.lower():
            candidate_names.add(original_story.lower())

        def _infer_navigation_from_element(label: str, role: str, tag: str) -> tuple[str, str]:
            label_clean = (label or "").strip()
            role_lower = (role or "").strip().lower()
            tag_lower = (tag or "").strip().lower()

            if role_lower in {"textbox", "input", "searchbox", "textarea", "password"} or tag_lower in {"input"}:
                pretty = label_clean or "Field"
                return (f"Enter {pretty}", f"{pretty}: <value>")
            if role_lower in {"combobox", "listbox", "select"} or tag_lower in {"select"}:
                pretty = label_clean or "Value"
                return (f"Select {pretty}", f"{pretty}: <value>")
            if role_lower in {"option", "radio", "menuitemradio"} or tag_lower in {"option"}:
                pretty = label_clean or "Option"
                return (f"Select the '{pretty}' option", "")
            if role_lower in {"checkbox", "switch", "menuitemcheckbox"} or tag_lower in {"input"} and "checkbox" in (label_clean.lower() if label_clean else ""):
                pretty = label_clean or "Option"
                noun = "checkbox" if role_lower == "checkbox" else "switch"
                return (f"Toggle the '{pretty}' {noun}", "")
            if role_lower == "button" or tag_lower in {"button"}:
                target = label_clean or "button"
                return (f"Click the '{target}' button", "")
            if role_lower == "link" or tag_lower == "a":
                target = label_clean or "link"
                return (f"Click the '{target}' link", "")
            if role_lower == "img" or tag_lower == "img":
                target = label_clean or "icon"
                return (f"Click on '{target}' icon", "")
            if role_lower == "cell" or tag_lower in {"td", "th"}:
                target = label_clean or "cell"
                return (f"Select the '{target}' cell", "")
            if role_lower == "tab":
                target = label_clean or "Tab"
                return (f"Open the '{target}' tab", "")
            if label_clean:
                return (f"Interact with '{label_clean}'", "")
            if role_lower:
                return (f"Interact with {role_lower}", "")
            if tag_lower:
                return (f"Interact with {tag_lower}", "")
            return ("Interact with element", "")

        def process_entry(entry: dict):
            if not entry:
                return
            meta = entry.get("metadata") or {}
            content = self._decode_vector_content(entry.get("content"))
            step_slug = str(
                meta.get("flow_slug")
                or content.get("flow_slug")
                or ""
            ).strip()
            step_name = str(
                meta.get("flow_name")
                or content.get("flow_name")
                or content.get("flow")
                or ""
            ).strip()
            step_slug_lower = step_slug.lower() if step_slug else ""
            step_name_lower = step_name.lower() if step_name else ""

            if candidate_slugs_lower and step_slug_lower and step_slug_lower not in candidate_slugs_lower:
                return
            if candidate_names and step_name_lower and step_name_lower not in candidate_names:
                return

            flow_hash = str(
                meta.get("flow_hash")
                or content.get("flow_hash")
                or ""
            ).strip()
            if flow_hash:
                flow_hashes.add(flow_hash)

            record_kind = (meta.get("record_kind") or content.get("record_kind") or "").strip().lower() or "step"
            if record_kind == "element":
                elem_index = content.get("element_index") or meta.get("element_index")
                try:
                    elem_index = int(elem_index)
                except (TypeError, ValueError):
                    elem_index = len(element_map) + 1
                label = (content.get("label") or meta.get("label") or "").strip()
                if not label:
                    return
                role = (content.get("role") or meta.get("role") or "").strip()
                tag = (content.get("tag") or meta.get("tag") or "").strip()
                locator_block = content.get("locators") or {}
                locators = locator_block if isinstance(locator_block, dict) else {}
                if not locators or "playwright" not in locators:
                    if role and label:
                        locators = {"playwright": {"byRole": {"role": role, "name": label}}}
                    else:
                        locators = {"playwright": {"byText": label}}
                navigation_text, data_text = _infer_navigation_from_element(label, role, tag)
                element_entry = {
                    "step": elem_index,
                    "action": label,
                    "navigation": navigation_text,
                    "data": data_text,
                    "expected": "",
                    "locators": {
                        **locators,
                        "labels": label,
                        "role": role,
                        "tag": tag,
                        "name": label,
                    },
                    "label": label,
                    "role": role,
                    "tag": tag,
                    "record_kind": "element",
                }
                element_map[elem_index] = element_entry
                # If we do not already have a richer step entry, synthesise one from the element.
                existing_step = steps_map.get(elem_index)
                if not existing_step or not any(existing_step.get(key) for key in ("navigation", "label", "locators")):
                    synthetic_navigation = navigation_text or label or role or tag or f"Element {elem_index}"
                    steps_map[elem_index] = {
                        "step": elem_index,
                        "action": label or synthetic_navigation,
                        "navigation": synthetic_navigation,
                        "data": data_text,
                        "expected": "",
                        "locators": element_entry.get("locators", {}),
                        "label": label,
                        "role": role,
                        "record_kind": "element",
                    }
                return

            step_index = content.get("step_index") or meta.get("step_index")
            try:
                step_index = int(step_index)
            except (TypeError, ValueError):
                step_index = len(steps_map) + 1
            action = content.get("action") or meta.get("action") or ""
            navigation = content.get("navigation") or meta.get("navigation") or ""
            data_val = content.get("data") or meta.get("data") or ""
            expected = content.get("expected") or meta.get("expected") or ""
            locators = content.get("locators") or {}
            label = (
                content.get("label")
                or meta.get("label")
                or (locators.get("labels") if isinstance(locators, dict) else "")
                or ""
            )
            existing = steps_map.get(step_index)
            if existing and existing.get("locators") and not locators:
                return
            steps_map[step_index] = {
                "step": step_index,
                "action": action,
                "navigation": navigation,
                "data": data_val,
                "expected": expected,
                "locators": locators,
                "label": label,
                "record_kind": record_kind or "step",
            }

        # Fetch all recorder entries for the flow via metadata filters (no similarity ranking).
        where_candidates: List[dict] = []
        if metadata_slug_filters:
            for slug_value in metadata_slug_filters:
                where_candidates.append({"type": "recorder_refined", "flow_slug": slug_value})
        if story_clean:
            where_candidates.append({"type": "recorder_refined", "flow_name": story_clean})
        if original_story and original_story.lower() != story_clean.lower():
            where_candidates.append({"type": "recorder_refined", "flow_name": original_story})

        metadata_limit = max(top_k, 256) * 4
        metadata_limit = max(metadata_limit, 1024)

        for where in where_candidates:
            try:
                records = self.db.list_where(where, limit=metadata_limit)
            except Exception as exc:
                logger.debug("Vector metadata fetch failed (%s): %s", where, exc)
                continue
            for entry in records or []:
                process_entry(entry)

        # If any flow hashes surfaced, hydrate the entire sequence for each hash.
        if flow_hashes:
            processed_hashes: set[str] = set()
            queue = [fh for fh in flow_hashes if fh]
            while queue:
                flow_hash = queue.pop(0)
                if flow_hash in processed_hashes:
                    continue
                processed_hashes.add(flow_hash)
                where = {"type": "recorder_refined", "flow_hash": flow_hash}
                try:
                    records = self.db.list_where(where, limit=metadata_limit)
                except Exception as exc:
                    logger.debug("Vector metadata fetch failed (%s): %s", where, exc)
                    continue
                for entry in records or []:
                    process_entry(entry)

        # As a final fallback (still no ranking), scan all recorder_refined entries and pick those matching the slug/name.
        if not steps_map and not element_map:
            try:
                all_records = self.db.list_where({"type": "recorder_refined"}, limit=metadata_limit)
            except Exception as exc:
                logger.debug("Vector metadata catch-all failed: %s", exc)
                all_records = []
            for entry in all_records or []:
                process_entry(entry)

        # Merge strategy: prefer chronological steps; append elements that don't duplicate them.
        if not steps_map and element_map:
            ordered_steps = [element_map[idx] for idx in sorted(element_map)]
            snippet_lines = [f"Element {item.get('step')}: {item.get('action')}" for item in ordered_steps[:12]]
            summary = f"Vector flow (elements): {story}\n" + "\n".join(snippet_lines)
            return [summary], ordered_steps

        if not steps_map and not element_map:
            return [], []

        # Start with steps in order
        ordered_steps = [element_map[idx] for idx in sorted(element_map)] if element_map else [steps_map[idx] for idx in sorted(steps_map)]
        combined = list(ordered_steps)

        # Helper to compute a dedupe signature similar to refined extractor
        def _sig(item: dict) -> tuple:
            loc = item.get("locators") or {}
            role = str(loc.get("role") or "").strip().lower()
            label = str((loc.get("labels") or loc.get("label") or loc.get("name") or item.get("action") or "")).strip().lower()
            tag = str(loc.get("tag") or "").strip().lower()
            pw = loc.get("playwright")
            if isinstance(pw, str):
                locator_sig = pw.strip()[:120]
            elif isinstance(pw, dict):
                by_role = pw.get("byRole") or {}
                locator_sig = f"{by_role.get('role','')}|{by_role.get('name','')}".strip().lower()
            else:
                locator_sig = ""
            step_id = str(item.get("step") or "")
            return (role, label, tag, locator_sig, step_id)

        seen = {_sig(s) for s in combined}

        # Append steps when no element map available (fallback to recorder steps)
        if not element_map and steps_map:
            for idx in sorted(steps_map):
                step_entry = steps_map[idx]
                signature = _sig(step_entry)
                if signature in seen:
                    continue
                combined.append(step_entry)
                seen.add(signature)

        # Append any remaining element entries not already included (for completeness)
        if element_map:
            for idx in sorted(element_map):
                elem = element_map[idx]
                signature = _sig(elem)
                if signature in seen:
                    continue
                combined.append(elem)
                seen.add(signature)

        # Build summary from first 12 entries
        snippet_lines = []
        for item in combined[:12]:
            descriptor = item.get("action") or item.get("navigation") or ""
            snippet_lines.append(f"Step {item.get('step')}: {descriptor}")

        summary = f"Vector flow: {story}\n" + "\n".join(snippet_lines)
        return [summary], combined

    def _decode_vector_content(self, raw_document) -> dict:
        if raw_document is None:
            return {}
        if isinstance(raw_document, dict):
            payload = raw_document.get("payload")
            return payload if isinstance(payload, dict) else raw_document
        raw_text = str(raw_document).strip()
        if not raw_text:
            return {}
        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError:
            try:
                data = ast.literal_eval(raw_text)
            except Exception:
                return {}
        if isinstance(data, dict) and "payload" in data and isinstance(data["payload"], dict):
            return data["payload"]
        return data if isinstance(data, dict) else {}

    def _ensure_vector_flow_ingested(self, story: str) -> bool:
        slug = slugify(story)
        if not GENERATED_DIR.exists():
            return False
        refined_files = sorted(GENERATED_DIR.glob("*.refined.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        ingested = False
        for path in refined_files:
            try:
                raw = path.read_text(encoding="utf-8")
                data = json.loads(raw)
            except Exception:
                continue
            flow_name = str(data.get("flow_name") or path.stem)
            flow_slug = slugify(flow_name)
            if slug and slug != "scenario" and slug not in flow_slug and flow_slug not in slug:
                continue
            try:
                ingest_refined_file(str(path), flow_name)
                ingested = True
                break
            except Exception as exc:
                logger.warning("Failed to ingest refined flow %s: %s", path, exc)
        return ingested

    def _load_saved_flows(self, story: str, limit: int = 3) -> Tuple[List[str], List[dict]]:
        flows_dir = Path(os.getcwd()) / "app" / "saved_flows"
        if not flows_dir.exists():
            return [], []

        key = re.sub(r"[^a-zA-Z0-9]", "", (story or "").lower())

        def normalize(text: str) -> str:
            return re.sub(r"[^a-zA-Z0-9]", "", (text or "").lower())

        snippets: List[str] = []
        structured_steps: List[dict] = []
        matched_any = False

        def build_humanized(path: Path, flow_title: str, steps: List[dict]) -> Optional[List[dict]]:
            enriched = self._load_enriched_steps(path.stem)
            humanized = enriched if enriched else self._humanize_flow_steps(steps, flow_title or path.stem)
            if not humanized:
                return None
            step_lines: List[str] = []
            for step in humanized[:12]:
                nav_text = step.get("navigation", "")
                data_text = step.get("data", "")
                descriptor = nav_text
                if data_text:
                    descriptor = f"{descriptor} | Data: {data_text}" if descriptor else f"Data: {data_text}"
                if step.get("expected"):
                    descriptor = f"{descriptor} | Expected: {step['expected']}" if descriptor else f"Expected: {step['expected']}"
                descriptor = descriptor or step.get("action", "")
                if descriptor:
                    step_lines.append(f"{step.get('step', '')}. {descriptor}".strip())
            snippet = "\n".join(step_lines)
            snippets.append(f"Saved flow: {path.name}\n{snippet}")
            return humanized

        # Prefer most recent flows by modification time
        flow_files = sorted(list(flows_dir.glob("*.json")), key=lambda p: p.stat().st_mtime, reverse=True)

        # First pass: match by filename or internal flow_name
        for path in flow_files:
            try:
                raw = path.read_text(encoding="utf-8")
                data = json.loads(raw)
            except Exception:
                continue
            flow_title = str(data.get("flow_name") or "")
            steps = data.get("steps") or []
            if key:
                stem_norm = normalize(path.stem)
                title_norm = normalize(flow_title)
                if key not in stem_norm and key not in title_norm:
                    continue
            humanized = build_humanized(path, flow_title, steps)
            if humanized and not structured_steps:
                structured_steps = humanized
            matched_any = True
            if len(snippets) >= limit:
                break

        return snippets, structured_steps

    def _load_refined_generated_flow(self, story: str, limit: int = 3) -> Tuple[List[str], List[dict]]:
        """Load refined generated flow JSON files from app/generated_flows that carry Playwright cues.
        Returns snippet strings for LLM context (if used) and a list of structured steps (original refined steps).
        """
        from pathlib import Path
        import json
        import re

        gen_dir = Path(os.getcwd()) / "app" / "generated_flows"
        if not gen_dir.exists():
            return [], []

        key = re.sub(r"[^a-zA-Z0-9]", "", (story or "").lower())

        def normalize(text: str) -> str:
            return re.sub(r"[^a-zA-Z0-9]", "", (text or "").lower())

        files = sorted(gen_dir.glob("*.refined.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        snippets: List[str] = []
        chosen_steps: List[dict] = []

        for path in files:
            try:
                raw = path.read_text(encoding="utf-8")
                data = json.loads(raw)
            except Exception:
                continue
            flow_title = str(data.get("flow_name") or path.stem)
            if key and key not in normalize(flow_title) and key not in normalize(path.stem):
                continue
            steps = data.get("steps") or []
            elements = data.get("elements") or []
            combined_steps = self._merge_refined_steps_with_elements(steps, elements)
            # Keep original refined steps plus derived elements; Playwright cues live under step["locators"]["playwright"]
            if combined_steps:
                # Build a compact snippet for context visibility
                lines = []
                for s in combined_steps[:12]:
                    nav = s.get("navigation") or ""
                    act = s.get("action") or ""
                    pl = (s.get("locators") or {}).get("playwright") or ""
                    label = (s.get("locators") or {}).get("labels") or ""
                    piece = act or nav or label or str(pl)
                    if piece:
                        lines.append(f"- {piece}")
                snippets.append(f"Refined flow: {path.name}\n" + "\n".join(lines))
                chosen_steps = combined_steps
                break

        return snippets, chosen_steps

    def _merge_refined_steps_with_elements(self, steps: List[dict], elements: List[dict]) -> List[dict]:
        """Combine refined recorder steps with standalone element metadata to maximise coverage."""
        combined = copy.deepcopy(steps) if steps else []

        def clean_label(value: Optional[str]) -> str:
            if value is None:
                return ""
            cleaned = str(value).strip()
            if not cleaned:
                return ""
            primary = cleaned.split("|", 1)[0].strip()
            return primary.rstrip(":").strip()

        seen_keys = set()
        unique_combined: List[dict] = []
        for item in combined:
            loc = item.get("locators") or {}
            role = str(loc.get("role") or "").strip().lower()
            tag = str(loc.get("tag") or "").strip().lower()
            label = clean_label(
                loc.get("labels")
                or loc.get("label")
                or loc.get("name")
                or item.get("label")
                or item.get("name")
            )
            navigation = str(item.get("navigation") or "").strip().lower()
            # Include locator signature and step id to avoid collapsing distinct steps with same label
            pw = (loc or {}).get("playwright")
            if isinstance(pw, str):
                locator_sig = pw.strip()[:120].lower()
            elif isinstance(pw, dict):
                br = pw.get("byRole") or {}
                locator_sig = f"{str(br.get('role') or '').lower()}|{str(br.get('name') or '').lower()}"
            else:
                locator_sig = ""
            step_id = str(item.get("step") or "")
            dedupe_key = (role, label.lower(), tag, navigation, locator_sig, step_id)
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
            unique_combined.append(item)

        combined = unique_combined

        for element in elements or []:
            role = str(element.get("role") or "").strip().lower()
            tag = str(element.get("tag") or "").strip().lower()
            label = clean_label(element.get("label") or element.get("name") or element.get("title"))
            if not label and tag in {"svg", "img", "path", "a"}:
                continue
            if not (label or role):
                continue
            # Use full label and locator signature for elements as well
            pw = element.get("playwright")
            if isinstance(pw, str):
                el_sig = pw.strip()[:120].lower()
            elif isinstance(pw, dict):
                br = pw.get("byRole") or {}
                el_sig = f"{str(br.get('role') or '').lower()}|{str(br.get('name') or '').lower()}"
            else:
                el_sig = ""
            el_step_id = str(element.get("element_index") or element.get("step") or "")
            dedupe_key = (role, label.lower(), tag, "", el_sig, el_step_id)
            if dedupe_key in seen_keys:
                continue
            locators = {
                "playwright": element.get("playwright") or "",
                "role": role,
                "labels": label,
                "label": element.get("label") or "",
                "name": element.get("name") or "",
                "tag": tag,
                "title": element.get("title") or "",
            }
            combined.append(
                {
                    "step": f"element-{len(combined) + 1}",
                    "action": element.get("action") or "",
                    "navigation": "",
                    "data": "",
                    "expected": "",
                    "locators": locators,
                }
            )
            seen_keys.add(dedupe_key)

        return combined

    def _load_enriched_steps(self, flow_name: str) -> Optional[List[dict]]:
        slug = slugify(flow_name)
        directory = GENERATED_DIR / slug
        if not directory.exists():
            return None

        csv_files = sorted(directory.glob("*.csv"))
        if not csv_files:
            return None

        latest_csv = max(csv_files, key=lambda p: p.stem)
        try:
            df = pd.read_csv(latest_csv)
        except Exception:
            return None

        structured: List[dict] = []
        sl_counter = 1
        current_action = ""
        for _, row in df.iterrows():
            action = str(row.get("Action", "") or "").strip()
            navigation = str(row.get("Navigation Steps", "") or "").strip()
            data_examples = str(row.get("Key Data Element Examples", "") or "").strip()
            expected = str(row.get("Expected Results", "") or "").strip()

            if action and action != current_action:
                current_action = action
                step_index = sl_counter
                sl_counter += 1
            else:
                step_index = len(structured) + 1

            structured.append(
                {
                    "step": step_index,
                    "action": action or current_action,
                    "navigation": navigation,
                    "data": data_examples,
                    "expected": expected,
                }
            )
        return structured if structured else None

    def _humanize_flow_steps(self, steps: List[dict], scenario_title: str = "") -> List[dict]:
        humanized: List[dict] = []
        if not steps:
            return humanized

        previous_section = scenario_title or ""
        default_section = scenario_title or "Scenario"

        for index, step in enumerate(steps, start=1):
            action_raw = str(step.get("action") or step.get("type") or "").lower()
            selector = step.get("selector") or step.get("target") or ""
            value = step.get("value") or step.get("text") or step.get("input") or ""
            description = step.get("description") or ""

            details = self._describe_recorder_step(action_raw, selector, value, description)
            navigation_text = details["navigation"]
            data_text = details["data"]
            expected_text = details["expected"]
            action_hint = details["action_hint"]

            section_label = self._infer_section_label(
                navigation_text,
                action_hint,
                default_section,
                previous_section,
                value,
                description,
            )

            humanized.append(
                {
                    "step": index,
                    "action": section_label,
                    "navigation": navigation_text,
                    "data": data_text,
                    "expected": expected_text,
                }
            )
            previous_section = section_label

        return humanized

    def _describe_recorder_step(self, action_raw: str, selector: str, value: str, description: str) -> dict:
        nav_text = ""
        data_text = ""
        expected_text = ""
        action_hint = ""

        if action_raw in {"goto", "navigate", "navigation"}:
            nav_text = f"Navigate to {value or self._clean_selector(selector)}"
            expected_text = "Target page is displayed."
            action_hint = "navigate"
            return {
                "navigation": self._apply_selector_hints(nav_text),
                "data": data_text,
                "expected": self._apply_expected_hints(nav_text, expected_text),
                "action_hint": action_hint,
            }

        nav_text, data_text, expected_text, action_hint = self._parse_selector_details(
            action_raw, selector, value, description
        )

        if not nav_text:
            nav_text = description or value or self._clean_selector(selector)
        nav_text = self._apply_selector_hints(nav_text)
        expected_text = self._apply_expected_hints(nav_text, expected_text)

        return {
            "navigation": nav_text.strip(),
            "data": data_text.strip(),
            "expected": expected_text.strip(),
            "action_hint": action_hint,
        }

    def _parse_selector_details(self, action_raw: str, selector: str, value: str, description: str):
        nav_text = ""
        data_text = ""
        expected_text = ""
        action_hint = ""

        text = selector or ""
        value = value or ""

        role_match = ROLE_PATTERN.search(text)
        name_match = NAME_PATTERN.search(text)
        label_match = LABEL_PATTERN.search(text)
        text_match = TEXT_PATTERN.search(text)
        placeholder_match = PLACEHOLDER_PATTERN.search(text)

        if role_match:
            role = role_match.group(1)
            name = name_match.group(1) if name_match else ""
            role_phrase = self._role_to_phrase(role)
            display_name = name or role_phrase or "element"

            if action_raw in {"click", "press"}:
                if role in {"tab"}:
                    action_hint = "select"
                    nav_text = f"Select the '{display_name}' {role_phrase}"
                else:
                    action_hint = "click"
                    nav_text = f"Click the '{display_name}' {role_phrase}"
            elif action_raw in {"fill", "type"}:
                action_hint = "enter data"
                nav_text = f"Enter {display_name}"
                data_text = f"{display_name}: {value}" if value else ""
                expected_text = "Value is captured."
            elif action_raw in {"select_option", "select"}:
                action_hint = "select"
                option = value or "the required option"
                nav_text = f"Select {option} in '{display_name}' {role_phrase}"
                if value:
                    data_text = f"{display_name}: {value}"
                expected_text = "Option is selected."
            elif action_raw in {"check", "uncheck"}:
                action_hint = "toggle"
                nav_text = f"{action_raw.capitalize()} the '{display_name}' {role_phrase}"
                expected_text = "Checkbox state updates."
            else:
                action_hint = action_raw or "click"
                nav_text = f"Interact with the '{display_name}' {role_phrase}"
        elif label_match:
            label = label_match.group(1)
            if action_raw in {"fill", "type"}:
                action_hint = "enter data"
                nav_text = f"Enter {label}"
                data_text = f"{label}: {value}" if value else ""
                expected_text = "Value is captured."
            elif action_raw in {"click", "press"}:
                action_hint = "click"
                nav_text = f"Click the '{label}' field"
            elif action_raw in {"check", "uncheck"}:
                action_hint = "toggle"
                nav_text = f"{action_raw.capitalize()} the '{label}' checkbox"
                expected_text = "Checkbox state updates."
        elif text_match:
            display = text_match.group(1)
            if action_raw in {"click", "press"}:
                action_hint = "click"
                nav_text = f"Click the '{display}' control"
            else:
                action_hint = action_raw or "interact"
                nav_text = f"Interact with '{display}'"
        elif placeholder_match:
            placeholder = placeholder_match.group(1)
            if action_raw in {"fill", "type"}:
                action_hint = "enter data"
                nav_text = f"Enter data in field with placeholder '{placeholder}'"
                data_text = f"{placeholder}: {value}" if value else ""
                expected_text = "Value is captured."
        elif "locator(" in text and "text=" in text:
            text_value = LOCATOR_TEXT_PATTERN.search(text)
            if text_value:
                display = text_value.group(1)
                if action_raw in {"click", "press"}:
                    action_hint = "click"
                    nav_text = f"Click the '{display}' control"
                else:
                    action_hint = action_raw or "interact"
                    nav_text = f"Interact with '{display}'"
        else:
            action_hint = action_raw or "interact"
            nav_text = description or self._clean_selector(selector)

        if action_raw in {"fill", "type"} and not data_text and value:
            field_name = self._extract_field_from_selector(selector) or "Field"
            data_text = f"{field_name}: {value}"
        if action_raw in {"select_option", "select"} and value and not data_text:
            field_name = self._extract_field_from_selector(selector) or "Selection"
            data_text = f"{field_name}: {value}"

        return nav_text, data_text, expected_text, action_hint

    def _clean_selector(self, selector: str) -> str:
        if not selector:
            return ""
        cleaned = selector.replace("xpath=", "").replace("locator=", "")
        # Strip Playwright prefixes without regex to avoid malformed patterns
        if "page." in cleaned:
            cleaned = cleaned.replace("page.", "")
        if ".click(" in cleaned:
            idx = cleaned.rfind(".click(")
            if idx != -1:
                cleaned = cleaned[:idx]
        # Collapse whitespace
        cleaned = " ".join(cleaned.split())
        return cleaned.strip()

    def _apply_selector_hints(self, text: str) -> str:
        lower = text.lower()
        for keyword, hint in SELECTOR_HINTS.items():
            if keyword in lower and hint not in text:
                if hint.startswith(" ") or hint.startswith("("):
                    text = f"{text}{hint}"
                else:
                    text = f"{text} {hint}"
        return text

    def _apply_expected_hints(self, navigation_text: str, expected_text: str) -> str:
        if expected_text:
            return expected_text
        lower = navigation_text.lower()
        for keyword, hint in EXPECTED_HINTS.items():
            if keyword in lower:
                return hint
        return expected_text or "Action completes successfully."

    def _infer_section_label(
        self,
        navigation_text: str,
        action_hint: str,
        default_section: str,
        previous_section: str,
        value: str,
        description: str,
    ) -> str:
        combined = " ".join(
            filter(
                None,
                [
                    navigation_text.lower(),
                    action_hint.lower() if action_hint else "",
                    (value or "").lower(),
                    (description or "").lower(),
                ],
            )
        )
        for keyword, label in SECTION_KEYWORDS:
            if keyword in combined:
                return label
        if action_hint:
            hint = action_hint.lower()
            if hint in {"click", "press"} and previous_section:
                return previous_section
            if hint == "navigate":
                return "Navigate"
            if hint in {"enter data", "select", "toggle"}:
                return previous_section or default_section
            return action_hint.capitalize()
        if previous_section:
            return previous_section
        return default_section

    def _role_to_phrase(self, role: Optional[str]) -> str:
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

    
    def _extract_field_from_selector(self, selector: str) -> str:
        if not selector:
            return ""
        label_match = LABEL_PATTERN.search(selector)
        if label_match:
            return label_match.group(1)
        name_match = NAME_PATTERN.search(selector)
        if name_match:
            return name_match.group(1)
        text_match = TEXT_PATTERN.search(selector)
        if text_match:
            return text_match.group(1)
        return ""

    def _flow_steps_prompt_json(self, flow_steps: List[dict]) -> str:
        summary: List[dict] = []
        for step in flow_steps:
            if not isinstance(step, dict):
                continue
            summary.append(
                {
                    "step": step.get("step"),
                    "action": step.get("action"),
                    "navigation": step.get("navigation"),
                    "data": step.get("data"),
                    "expected": step.get("expected"),
                    "label": step.get("label"),
                    "role": step.get("role"),
                    "locator": step.get("locator"),
                    "record_kind": step.get("record_kind"),
                }
            )
        return json.dumps(summary, ensure_ascii=False)

    def _build_recorder_element_chunks(self, steps: List[dict]) -> Tuple[List[str], List[str]]:
        def sanitize_label(value: Optional[str]) -> str:
            if value is None:
                return ""
            text = str(value).strip()
            if not text:
                return ""
            primary = text.split("|", 1)[0].strip()
            return primary.rstrip(":").strip()

        lines: List[str] = []
        sources: List[str] = []

        for idx, step in enumerate(steps, start=1):
            locators = step.get("locators") or {}
            role = str(locators.get("role") or "").strip()
            labels_field = locators.get("labels") or locators.get("label") or locators.get("name")
            if isinstance(labels_field, (list, tuple, set)):
                label = ", ".join(sanitize_label(part) for part in labels_field if part)
            else:
                label = sanitize_label(labels_field)
            if not label and locators.get("playwright"):
                label = sanitize_label(locators.get("playwright"))

            action = str(step.get("action") or "").strip()
            navigation = str(step.get("navigation") or "").strip()

            if not (label or role):
                if navigation:
                    label = navigation
                else:
                    continue

            role_display = role or "unknown"
            lines.append(f"{idx:02d}. role={role_display} | label={label or '(missing label)'} | action={action}")
            descriptor = label or action or f"step-{idx}"
            sources.append(f"recorder_refined:{descriptor}")

        if not lines:
            return [], sources
        return ["Recorder refined element cues:\n" + "\n".join(lines)], sources

    def _build_generation_prompt(self, story: str, context: str, flow_steps_json: str, positive_outline_json: Optional[str] = None) -> str:
        fields = ", ".join(self.default_fields)
        outline_section = ""
        if positive_outline_json:
            outline_section = (
                "Positive flow outline (assembled from chunked step rewrites; maintain this order and ensure every step id is represented once):\n"
                f"{positive_outline_json}\n\n"
            )
        return (
            "You are an expert QA engineer for Oracle Fusion / enterprise web flows.\n"
            "Using ONLY the retrieved context, derive comprehensive, professional manual test cases covering positive, negative, and edge scenarios.\n"
            f"The user supplied keywords or artifact name: '{story}'.\n"
            "Context snippets (prioritise Playwright flows, repo scaffolds, Jira docs):\n"
            f"{context}\n\n"
            "You are also provided sanitized recorder element cues per step. Each item contains: the recorder step index, the intended action verb, the captured UI label(s), the ARIA role (if available), and a concise locator hint (no XPath data).\n"
            "For the primary positive scenario, mirror these steps in order, deriving navigation wording directly from the element labels and role context (do not invent new UI names). Expand the labels into detailed actions with explicit navigation, data entry, and observable expected outcomes.\n"
            f"{outline_section}"
            f"Recorder element cues JSON:\n{flow_steps_json}\n\n"
            "Additionally, for EACH core step in the positive flow (up to 6-8 main steps), generate at least one negative and one edge case focusing on that step's validation (e.g., required field empty, invalid format, unauthorized action, boundary values). Keep these as separate cases with precise 'type' values and step-by-step actions.\n\n"
            "Output strictly as a JSON array. Respond with ONLY the JSON array - no prose, no explanations, no code fences. Each element must contain the fields: "
            f"{fields}, plus an additional field 'step_details'.\n"
            "'step_details' must be an ordered list of objects with keys:\n"
            "- action: High-level activity label (e.g., 'Log into Oracle', 'Navigate to Payables', 'Create Supplier').\n"
            "- navigation: Exact UI navigation or click sequence (string; multiple lines allowed using \\n).\n"
            "- data: Key data inputs for that step (string summarising field-value pairs; empty string if none).\n"
            "- expected: Immediate system response/validation (string; empty string if none).\n\n"
            "Rules:\n"
            "- Treat each test case as a manual QA script suitable for handover to a test team.\n"
            "- Produce at least one positive overall, and per-step variants: for each core step of the positive flow, add one negative and one edge case focused on that step.\n"
            "- 'type' must be one of ['positive', 'negative', 'edge'].\n"
            "- 'steps' should mirror 'step_details' but as plain text summaries (list of strings) written as executable manual instructions.\n"
            "- Include concrete preconditions, required data/test accounts (use the 'data' field), and expected results with clear pass/fail criteria.\n"
            "- Reference Oracle screen names, navigation breadcrumbs, field labels, and validation messages exactly as they appear in the context.\n"
            "- When context provides IDs, error messages, or business rules, surface them in the relevant steps and expected results.\n"
            "- Negative and edge cases must be grounded in the retrieved artefacts (e.g., validation rules, error handling, alternate flows) or clearly state assumptions if inferred.\n"
            "- If you must assume anything, list it in 'assumptions'; otherwise use an empty list.\n"
            "- Use realistic Oracle Fusion terminology (e.g., 'Navigator > Procurement > Suppliers').\n"
            "- Ensure each case covers an end-to-end workflow, not just authentication, and ties outcomes to business results.\n"
            "- Keep language precise, imperative, and free of AI hedging (no 'maybe', 'could').\n"
            "- All values must be valid JSON strings (no expressions like \"a\".repeat(3)).\n"
            "- Double-check that the positive scenario covers every recorder step index supplied. If anything cannot be covered, list the missing indices under 'assumptions'.\n"
            "- If context is limited, propose the most probable flow and document assumptions explicitly.\n"
        )

    def _build_manual_table_prompt(self, flow_name: str, db_query: str, scope: str, flow_steps: List[dict]) -> str:
        """Load the manual table system/developer prompt and fill placeholders.
        Embeds a compact view of refined steps to ground the model.
        """
        prompt_path = Path(os.getcwd()) / "app" / "prompts" / "manual_table_prompt.md"
        try:
            template = prompt_path.read_text(encoding="utf-8")
        except Exception:
            # Minimal fallback if file missing
            template = (
                "Role (System)\nYou are a QA agent. Output a markdown table: sl | Action | Navigation Steps | Key Data Element Examples | Expected Results.\n"
            )

        # Build a compact context from refined steps
        def _compact_step(s: dict) -> str:
            loc = (s.get("locators") or {})
            pw = (loc.get("playwright") or "")
            role = loc.get("role") or ""
            name = loc.get("name") or loc.get("labels") or ""
            tag = loc.get("tag") or ""
            if isinstance(pw, dict):
                byrole = pw.get("byRole") or {}
                bytext = pw.get("byText") or ""
                if byrole and (byrole.get("role") or byrole.get("name")):
                    role = byrole.get("role") or role
                    name = byrole.get("name") or name
                    pw = f"getByRole('{role}', {{ name: '{name}' }})"
                elif isinstance(bytext, str) and bytext:
                    pw = f"getByText('{bytext}')"
            return f"step={s.get('step','')}, action={s.get('action','')}, pw={pw}, role={role}, name={name}, tag={tag}"

        compact = "\n".join(_compact_step(s) for s in (flow_steps or [])[:50])
        payload = (
            template
            .replace("{{flow_name}}", flow_name or "")
            .replace("{{db_query}}", db_query or (flow_name or ""))
            .replace("{{scope}}", scope or "")
        )
        payload += "\n\nContext (refined steps, compact):\n" + compact + "\n"
        return payload

    def generate_manual_table(
        self,
        story: str,
        db_query: Optional[str] = None,
        scope: Optional[str] = None,
        coverage: str = "grouped",
        include_unlabeled: bool = False,
        include_login: bool = False,
    ) -> str:
        """Generate a markdown table.

        Args:
            story: Flow name used to locate refined steps.
            db_query: Optional vector DB query override.
            scope: Optional textual hint.
            coverage: "grouped" (default) groups steps into friendly sections;
                      "full" returns ALL extracted micro-steps without grouping.
            include_unlabeled: When True, include unlabeled icon/anchor elements
                               with generic phrasing (helps capture Navigator/Task icons, etc.).

        Returns:
            Markdown table text.
        """
        context_chunks, flow_steps, _ = self._collect_context(story)
        manual_steps: List[dict] = []
        if flow_steps:
            if any(isinstance(step, dict) and (step.get("locators") or {}).get("playwright") for step in flow_steps):
                # Build directly from refined recorder cues
                manual_steps = self._build_manual_steps_from_refined(flow_steps, include_unlabeled=include_unlabeled)
            else:
                manual_steps = [
                    {
                        "action": step.get("action", ""),
                        "navigation": step.get("navigation", ""),
                        "data": step.get("data", ""),
                        "expected": step.get("expected", ""),
                    }
                    for step in flow_steps
                    if step and (step.get("navigation") or step.get("data") or step.get("expected") or step.get("action"))
                ]

        if manual_steps:
            if include_login:
                manual_steps = self._maybe_prepend_login_steps(manual_steps)
            if str(coverage).lower() == "full":
                # Return raw extracted micro-steps without grouping or rewriting
                return self._manual_steps_to_markdown(manual_steps)
            # Otherwise, keep the current phrasing/grouping behavior
            refined = self._refine_manual_steps_phrasing(manual_steps)
            return self._manual_steps_to_markdown(refined)

        prompt = self._build_manual_table_prompt(
            flow_name=story,
            db_query=db_query or story,
            scope=scope or "",
            flow_steps=flow_steps,
        )
        resp = self.llm.invoke(prompt)
        content = resp.content if hasattr(resp, "content") else str(resp)
        return content.strip()

    # ----------------- Variant expansion helpers -----------------
    def _ensure_per_step_variants(
        self,
        cases: List[dict],
        flow_steps: List[dict],
        per_step_negatives: int,
        per_step_edges: int,
        max_steps: int,
        story: str,
    ) -> List[dict]:
        if not cases:
            return cases
        # Find a base positive case to expand
        base = None
        for c in cases:
            if str(c.get("type", "")).lower() == "positive" and c.get("step_details"):
                base = c
                break
        if not base:
            # Try to synthesize from flow steps if available
            if flow_steps:
                synthesized = self._fallback_from_flow(story, flow_steps)[0]
                base = synthesized
                cases.insert(0, synthesized)
            else:
                return cases

        existing_counts = {}
        for c in cases:
            t = str(c.get("type", "")).lower()
            existing_counts[t] = existing_counts.get(t, 0) + 1

        step_details = base.get("step_details", [])
        if not isinstance(step_details, list) or not step_details:
            return cases

        # Cap to first N steps to avoid explosion
        limit = min(max_steps, len(step_details))

        next_id_num = len(cases) + 1
        def _next_id(prefix: str) -> str:
            nonlocal next_id_num
            val = f"{prefix}{next_id_num:03}"
            next_id_num += 1
            return val

        new_cases: List[dict] = []
        for idx in range(limit):
            base_step = step_details[idx]
            # Generate negative variants
            for _ in range(max(0, per_step_negatives)):
                neg_case = self._make_negative_variant(base, idx)
                neg_case["id"] = _next_id("TCN")
                neg_case["tags"] = list(set((neg_case.get("tags") or []) + [f"per-step-variant:{idx+1}"]))
                new_cases.append(neg_case)
            # Generate edge variants
            for _ in range(max(0, per_step_edges)):
                edge_case = self._make_edge_variant(base, idx)
                edge_case["id"] = _next_id("TCE")
                edge_case["tags"] = list(set((edge_case.get("tags") or []) + [f"per-step-variant:{idx+1}"]))
                new_cases.append(edge_case)

        # Append new variants
        cases.extend(new_cases)
        return cases

    def _clone_case(self, case: dict) -> dict:
        import copy
        return copy.deepcopy(case)

    def _make_negative_variant(self, base_case: dict, step_index: int) -> dict:
        case = self._clone_case(base_case)
        case["type"] = "negative"
        base_title = str(base_case.get("title") or "Scenario")
        case["title"] = f"{base_title} - Negative at Step {step_index+1}"
        details = case.get("step_details", [])
        # Adjust the focus step with invalid/missing data
        if 0 <= step_index < len(details):
            target = details[step_index]
            nav = target.get("navigation", "")
            # Heuristic: if it's a data entry step, blank the data; else insert an invalid value
            data_val = target.get("data", "")
            if data_val:
                target["data"] = self._mutate_data_invalid(data_val)
            else:
                target["data"] = "<required>: (empty)"
            target["expected"] = target.get("expected") or "Validation error is displayed; system prevents save."
        # Trim steps after failure point to keep scenario focused
        case["step_details"] = details[: step_index + 1]
        case["steps"] = [
            f"{d.get('action','')} - {d.get('navigation','')}".strip(" -") + (f" | Data: {d['data']}" if d.get('data') else '') + (f" | Expected: {d['expected']}" if d.get('expected') else '')
            for d in case["step_details"]
        ]
        case["expected"] = case["step_details"][-1].get("expected", "")
        return case

    def _make_edge_variant(self, base_case: dict, step_index: int) -> dict:
        case = self._clone_case(base_case)
        case["type"] = "edge"
        base_title = str(base_case.get("title") or "Scenario")
        case["title"] = f"{base_title} - Edge at Step {step_index+1}"
        details = case.get("step_details", [])
        if 0 <= step_index < len(details):
            target = details[step_index]
            data_val = target.get("data", "")
            target["data"] = self._mutate_data_edge(data_val)
            target["expected"] = target.get("expected") or "System handles boundary value gracefully."
        case["step_details"] = details[: step_index + 1] + details[step_index + 1:]
        case["steps"] = [
            f"{d.get('action','')} - {d.get('navigation','')}".strip(" -") + (f" | Data: {d['data']}" if d.get('data') else '') + (f" | Expected: {d['expected']}" if d.get('expected') else '')
            for d in case["step_details"]
        ]
        case["expected"] = details[step_index].get("expected", case.get("expected", ""))
        return case

    def _mutate_data_invalid(self, data_str: str) -> str:
        # Simple heuristic mutations: empty required; invalid email; invalid number
        lower = data_str.lower()
        if "email" in lower:
            return data_str + " | email: not-an-email"
        if any(k in lower for k in ["amount", "qty", "quantity", "number", "rate"]):
            return data_str + " | amount: -1"
        if any(k in lower for k in ["date", "dob", "effective"]):
            return data_str + " | date: 31-02-2025"
        # Default: required missing
        return data_str + " | <required>: (empty)"

    def _mutate_data_edge(self, data_str: str) -> str:
        lower = data_str.lower()
        if any(k in lower for k in ["name", "supplier", "description"]):
            return data_str + " | name: 'A' * 255"
        if any(k in lower for k in ["amount", "qty", "quantity", "number", "rate"]):
            return data_str + " | amount: 999999999"
        if any(k in lower for k in ["date", "dob", "effective"]):
            return data_str + " | date: 29-02-2024"
        return data_str + " | note: boundary conditions applied"

    def _normalize_llm_json(self, text: str) -> str:
        def replace_repeat(match: re.Match) -> str:
            key = match.group(1)
            base = match.group(2)
            count = int(match.group(3))
            repeated = base * min(count, 512)
            repeated = repeated.replace('"', '\\"')
            return f'"{key}": "{repeated}"'

        pattern = re.compile(r'"([^"]+)"\s*:\s*"([^"\\]*)"\.repeat\((\d+)\)')
        text = pattern.sub(replace_repeat, text)
        text = re.sub(r"\\n", " ", text)
        return text

    def _enforce_schema(self, cases) -> List[dict]:
        if not isinstance(cases, list):
            raise ValueError("LLM output must be a JSON array of cases.")
        cleaned: List[dict] = []
        allowed_types = {"positive", "negative", "edge"}

        def _ensure_title_with_type(title: str, ctype: str) -> str:
            text = title.strip()
            lower = text.lower()
            if ctype == "positive":
                if "positive" not in lower:
                    suffix = "Positive Scenario"
                else:
                    return text or "Positive Scenario"
            elif ctype == "negative":
                if "negative" not in lower:
                    suffix = "Negative Scenario"
                else:
                    return text or "Negative Scenario"
            else:
                if "edge" not in lower:
                    suffix = "Edge Scenario"
                else:
                    return text or "Edge Scenario"
            return f"{text + ' - ' if text else ''}{suffix}"

        for idx, case in enumerate(cases, start=1):
            if not isinstance(case, dict):
                continue
            normalized = {}
            normalized["id"] = str(case.get("id") or f"TC{idx:03}")
            normalized["title"] = str(case.get("title") or f"Scenario {idx}")
            ctype = str(case.get("type") or "positive").lower()
            if ctype not in allowed_types:
                ctype = "edge" if "edge" in ctype else "negative" if "fail" in ctype else "positive"
            normalized["type"] = ctype
            normalized["title"] = _ensure_title_with_type(normalized["title"], ctype)

            preconditions = case.get("preconditions") or []
            if isinstance(preconditions, str):
                preconditions = [p.strip() for p in preconditions.split("\n") if p.strip()]
            normalized["preconditions"] = preconditions if isinstance(preconditions, list) else []

            raw_step_details = case.get("step_details") or []
            step_details = []
            if isinstance(raw_step_details, list):
                for step_idx, step in enumerate(raw_step_details, start=1):
                    if isinstance(step, dict):
                        action = str(step.get("action", "")).strip()
                        navigation = str(step.get("navigation", "")).strip()
                        data_value = step.get("data", "")
                        expected = str(step.get("expected", "")).strip()
                        if isinstance(data_value, (list, dict)):
                            data_value = json.dumps(data_value, ensure_ascii=False)
                        data_value = str(data_value).strip()
                        if not any([action, navigation, data_value, expected]):
                            continue
                        step_details.append({
                            "action": action,
                            "navigation": navigation,
                            "data": data_value,
                            "expected": expected,
                        })
                    elif isinstance(step, str):
                        text = step.strip()
                        if text:
                            step_details.append({
                                "action": "",
                                "navigation": text,
                                "data": "",
                                "expected": "",
                            })
            steps = case.get("steps") or []
            if isinstance(steps, str):
                steps = [s.strip() for s in steps.split("\n") if s.strip()]
            if not steps and step_details:
                steps = [
                    f"{detail.get('action', '')} - {detail.get('navigation', '')}".strip(" -")
                    for detail in step_details
                ]
            normalized["step_details"] = step_details
            normalized["steps"] = steps if isinstance(steps, list) else []

            data_field = case.get("data") or case.get("test_data") or {}
            if isinstance(data_field, list):
                data_field = {f"data_{i+1}": v for i, v in enumerate(data_field)}
            if not isinstance(data_field, dict):
                data_field = {"value": str(data_field)}
            normalized["data"] = data_field

            normalized["expected"] = str(case.get("expected") or "")
            normalized["priority"] = str(case.get("priority") or "medium")

            tags = case.get("tags") or []
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",") if t.strip()]
            normalized["tags"] = tags if isinstance(tags, list) else []

            assumptions = case.get("assumptions") or []
            if isinstance(assumptions, str):
                assumptions = [a.strip() for a in assumptions.split("\n") if a.strip()]
            normalized["assumptions"] = assumptions if isinstance(assumptions, list) else []

            if not normalized["step_details"] and not normalized["steps"]:
                continue
            cleaned.append(normalized)
        return cleaned

    def _inject_flow_details(self, cases: List[dict], flow_steps: List[dict], context_sources: List[str]) -> List[dict]:
        if not cases:
            return cases

        if flow_steps:
            # If refined steps with Playwright cues are present, transform them into clean manual steps
            if any(isinstance(it, dict) and (it.get("locators") or {}).get("playwright") for it in flow_steps):
                step_details = self._build_manual_steps_from_refined(flow_steps)
            else:
                step_details = [
                    {
                        "action": item.get("action", ""),
                        "navigation": item.get("navigation", ""),
                        "data": item.get("data", ""),
                        "expected": item.get("expected", ""),
                    }
                    for item in flow_steps
                ]

            step_strings = []
            for detail in step_details:
                action = detail.get("action", "")
                navigation = detail.get("navigation", "")
                data = detail.get("data", "")
                expected = detail.get("expected", "")
                parts = [part for part in [action, navigation] if part]
                if data:
                    parts.append(f"Data: {data}")
                if expected:
                    parts.append(f"Expected: {expected}")
                step_strings.append(" - ".join(parts).strip(" -"))

            injected = False
            for case in cases:
                if case.get("type") == "positive" and not injected:
                    case["step_details"] = step_details
                    case["steps"] = step_strings
                    if not case.get("expected") and step_details[-1].get("expected"):
                        case["expected"] = step_details[-1]["expected"]
                    injected = True

            if not injected:
                cases[0]["step_details"] = step_details
                cases[0]["steps"] = step_strings
                if not cases[0].get("expected") and step_details[-1].get("expected"):
                    cases[0]["expected"] = step_details[-1]["expected"]
        else:
            if context_sources:
                formatted_sources = []
                for item in context_sources[:3]:
                    if ":" in item:
                        src, desc = item.split(":", 1)
                        formatted_sources.append(f"{src.strip()} -> {desc.strip()}")
                    else:
                        formatted_sources.append(item)
                provenance = ", ".join(formatted_sources)
            else:
                provenance = "Jira / documents / repository sources"
            note = (
                f"No recorder flow available. Sequential steps derived from {provenance}."
            )
            for case in cases:
                assumptions = case.get("assumptions") or []
                if isinstance(assumptions, str):
                    assumptions = [assumptions] if assumptions else []
                if note not in assumptions:
                    assumptions.append(note)
                case["assumptions"] = assumptions

        return cases

    # ----------------- Refined Playwright cues -> manual steps -----------------
    def _build_manual_steps_from_refined(self, refined_steps: List[dict], include_unlabeled: bool = False) -> List[dict]:
        """Build manual steps from refined Playwright cues in a generic, data-driven way.
        Rules:
        - Use only Playwright getByRole/getByText/getByLabel cues; ignore raw CSS/XPath.
        - Do not hardcode domain values or flow-specific text; derive labels from the cues.
        - Generate generic navigation/data/expected phrasing based on the role and label text.
        - By default skip anonymous svg/img/path/a elements with no label. Set include_unlabeled=True
          to include them with generic phrasing (helps capture icon clicks and anchors).
        """
        def parse_playwright(locators: dict) -> tuple[str, str]:
            pw = (locators or {}).get("playwright")
            if isinstance(pw, dict):
                # Newer enriched shape
                br = pw.get("byRole")
                if isinstance(br, dict) and br.get("role"):
                    role = str(br.get("role") or "").strip()
                    name = str(br.get("name") or "").strip()
                    return (f"role:{role}", name)
                bt = pw.get("byText")
                if isinstance(bt, str) and bt.strip():
                    return ("text", bt.strip())
                bl = pw.get("byLabel")
                if isinstance(bl, str) and bl.strip():
                    return ("role:textbox", bl.strip())
            s = str(pw or "")
            if not s:
                return ("none", "")
            m = re.search(r"getByRole\(\s*'([^']+)'\s*,\s*\{\s*name\s*:\s*'([^']+)'\s*}\s*\)", s)
            if m:
                return (f"role:{m.group(1)}", m.group(2))
            m2 = re.search(r"getByText\(\s*['\"]([^'\"]+)['\"]\s*\)", s)
            if m2:
                return ("text", m2.group(1))
            return ("none", "")

        def generic_expected(role: str, label: str, nav_text: str) -> str:
            lrole = (role or "").lower()
            lnav = (nav_text or "").lower()
            llabel = (label or "").strip()
            if "tab" in lrole or " tab" in lnav:
                return f"'{llabel}' tab opened" if llabel else "Tab opened"
            if any(kw in lnav for kw in ["open", "navigate", "go to"]):
                return "Target page is displayed"
            if any(kw in lnav for kw in ["enter", "fill", "type"]):
                return "Value is captured"
            if any(kw in lnav for kw in ["select", "choose", "pick"]):
                return "Option is selected"
            if any(kw in lnav for kw in ["check", "uncheck", "toggle", "click", "press", "submit"]):
                return "Action completes successfully."
            return "Action completes successfully."

        entry_roles = {"textbox", "input", "searchbox", "textarea", "password"}
        select_roles = {"combobox", "listbox", "select"}
        option_roles = {"option", "radio", "menuitemradio"}
        toggle_roles = {"checkbox", "switch", "menuitemcheckbox", "togglebutton"}
        click_phrases = {
            "button": "Click the {label} button",
            "link": "Click the {label} link",
            "img": "Click on {label} icon",
            "menuitem": "Select the {label} menu option",
            "treeitem": "Expand {label}",
            "cell": "Select the {label} cell",
            "row": "Select the {label} row",
            "gridcell": "Select the {label} cell",
        }

        def sanitize_label(text: Optional[str]) -> str:
            if not text:
                return ""
            cleaned = str(text).strip()
            if not cleaned:
                return ""
            primary = cleaned.split("|", 1)[0].strip()
            return primary.rstrip(":").strip()

        def quote_label(label_text: str) -> str:
            if not label_text:
                return ""
            quote_char = "'" if "'" not in label_text else '"'
            return f"{quote_char}{label_text}{quote_char}"

        out: List[dict] = []
        seen_keys: set = set()

        for step in refined_steps:
            loc = step.get("locators") or {}
            kind, value = parse_playwright(loc)
            raw_role = str(loc.get("role") or "").strip().lower()
            tag = str(loc.get("tag") or "").strip().lower()
            role = kind.split(":", 1)[1] if kind.startswith("role:") else raw_role
            if not role:
                if tag == "button":
                    role = "button"
                elif tag == "a":
                    role = "link"
            label_candidates = [
                value,
                loc.get("labels"),
                loc.get("label"),
                loc.get("name"),
                loc.get("title"),
                step.get("label"),
                step.get("name"),
            ]
            label = ""
            for candidate in label_candidates:
                label = sanitize_label(candidate)
                if label:
                    break

            if not label and tag in {"svg", "img", "path", "a"}:
                if not include_unlabeled:
                    continue

            nav_text = ""
            data_text = ""
            quoted = quote_label(label)

            if kind == "text" and label:
                nav_text = f"Click on {quoted}"
            elif role in entry_roles:
                pretty = label or "Field"
                nav_text = f"Enter {pretty}"
                data_text = f"{pretty}: <value>"
            elif role in select_roles:
                pretty = label or "Value"
                nav_text = f"Select {pretty}"
                data_text = f"{pretty}: <value>"
            elif role in option_roles:
                pretty = label or "Option"
                nav_text = f"Select the {quote_label(pretty)} option"
            elif role in toggle_roles:
                pretty = label or "Option"
                noun = "checkbox" if role == "checkbox" else "switch" if role == "switch" else "option"
                verb = "Toggle" if role in {"checkbox", "switch", "menuitemcheckbox"} else "Select"
                nav_text = f"{verb} the {quote_label(pretty)} {noun}".strip()
            elif role == "tab" and label:
                nav_text = f"Open the {quoted} tab"
            elif role in click_phrases and label:
                nav_text = click_phrases[role].format(label=quoted)

            if not nav_text:
                if label:
                    nav_text = f"Click on {quoted}"
                elif include_unlabeled:
                    # Use any available hint for a generic phrase
                    title_hint = str((step.get("locators") or {}).get("title") or "").strip()
                    hint = title_hint or role or tag or "element"
                    verb = "Click"
                    if role in {"checkbox", "switch"}:
                        verb = "Toggle"
                    nav_text = f"{verb} the {hint}"
                else:
                    continue

            if not nav_text:
                continue

            # Make de-duplication resilient for unlabeled elements by including a locator signature
            locator_sig = ""
            pw = (loc or {}).get("playwright")
            if isinstance(pw, str):
                locator_sig = pw.strip()[:120]
            elif isinstance(pw, dict):
                by_role = pw.get("byRole") or {}
                locator_sig = f"{by_role.get('role','')}|{by_role.get('name','')}".strip()
            step_id = str(step.get("step") or "")
            dedupe_key = (
                (role or "").lower(),
                (label.lower() if label else locator_sig or step_id),
                nav_text.lower(),
                data_text.lower() if data_text else "",
            )
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)

            out.append(
                {
                    "action": "",
                    "navigation": nav_text,
                    "data": data_text,
                    "expected": generic_expected(role, label, nav_text),
                    "label": label,
                    "role": role,
                }
            )
        # End of Task line
        if not out or out[-1].get("navigation") != "End of Task":
            out.append({"action": "End of Task", "navigation": "End of Task", "data": "", "expected": ""})

        # Coalesce empty actions under previous non-empty
        normalized: List[dict] = []
        last_action = ""
        for d in out:
            act = str(d.get("action", "")).strip()
            if not act:
                d["action"] = last_action
            else:
                last_action = act
            normalized.append(d)
        return normalized

    def _maybe_prepend_login_steps(self, steps: List[dict]) -> List[dict]:
        """Prepend a generic Oracle login step if one is not already present.

        Detection: If any existing step mentions login/sign in or contains username/password fields, we assume
        login is already covered and do nothing. Otherwise, we add a consolidated first step capturing the
        homepage, login click, credentials, and success expectation.
        """
        try:
            joined = "\n".join([
                f"{s.get('action','')}\n{s.get('navigation','')}\n{s.get('data','')}\n{s.get('expected','')}"
                for s in (steps or [])
            ]).lower()
        except Exception:
            joined = ""

        tokens = [
            "login", "log in", "sign in", "signin", "user name", "username", "password",
        ]
        if any(t in joined for t in tokens):
            return steps

        login_step = {
            "action": "Log into Oracle",
            "navigation": "Login to Oracle Cloud Applications Homepage\nClick Login",
            "data": "Enter User Name\nEnter Password",
            "expected": "Login Successful",
        }
        return [login_step] + (steps or [])

    def _manual_steps_to_markdown(self, manual_steps: List[dict]) -> str:
        """Render manual step dictionaries as a markdown table."""
        rows: List[Tuple[int, str, str, str, str]] = []
        sl_counter = 1
        default_action = manual_steps[0].get("action", "Scenario") if manual_steps else "Scenario"
        previous_action = ""
        last_action_written: Optional[str] = None

        def escape_cell(value: str) -> str:
            return value.replace("|", "\\|")

        for detail in manual_steps:
            navigation_value = str(detail.get("navigation", "")).strip()
            data_value = str(detail.get("data", "")).strip()
            expected_value = str(detail.get("expected", "")).strip()
            if not any([navigation_value, data_value, expected_value, detail.get("action", "")]):
                continue

            action_value = _derive_manual_action(detail, default_action, previous_action)

            display_action = action_value
            if last_action_written is not None and action_value == last_action_written:
                display_action = ""
            else:
                last_action_written = action_value

            rows.append(
                (
                    sl_counter,
                    escape_cell(display_action),
                    escape_cell(navigation_value),
                    escape_cell(data_value),
                    escape_cell(expected_value),
                )
            )

            previous_action = action_value
            sl_counter += 1

        header = "| sl | Action | Navigation Steps | Key Data Element Examples | Expected Results |\n"
        header += "| --- | --- | --- | --- | --- |\n"
        body_lines = [
            f"| {sl} | {action} | {navigation} | {data} | {expected} |"
            for sl, action, navigation, data, expected in rows
        ]
        return header + "\n".join(body_lines)

    def _refine_manual_steps_phrasing(self, manual_steps: List[dict]) -> List[dict]:
        """Adjust phrasing for common Oracle navigation/data patterns."""
        refined: List[dict] = []
        navigator_added = False
        nav_map = {
            "navigator": {
                "action": "Navigate",
                "navigation": "Click the Navigator link",
                "data": "",
                "expected": "Navigator menu is displayed.",
            },
            "procurement": {
                "action": "Navigate",
                "navigation": "Click the Suppliers link under the Procurement category",
                "data": "",
                "expected": "Procurement module is displayed.",
            },
            "tasks": {
                "action": "Navigate",
                "navigation": "Click the Task Pane icon (Sheet of Paper)",
                "data": "",
                "expected": "Tasks pane opens.",
            },
            "create supplier": {
                "action": "Navigate",
                "navigation": "Click Create Supplier hyperlink in the Tasks region",
                "data": "",
                "expected": "Create Supplier form is displayed.",
            },
        }
        data_map = {
            "supplier": {
                "action": "Create a Supplier",
                "navigation": "Enter Supplier Name in the Supplier field",
                "data": "Enter a unique Supplier Name",
                "expected": "Field captures the supplier name.",
            },
            "business relationship": {
                "action": "Create a Supplier",
                "navigation": "Select Business Relationship",
                "data": "Spend Authorized",
                "expected": "Business relationship is selected.",
            },
            "tax organization type": {
                "action": "Create a Supplier",
                "navigation": "Select Tax Organization Type",
                "data": "Corporation",
                "expected": "Tax organization type is selected.",
            },
            "tax country": {
                "action": "Create a Supplier",
                "navigation": "Select Tax Country",
                "data": "United States",
                "expected": "Tax country is selected.",
            },
            "create": {
                "action": "Submit Supplier Creation",
                "navigation": "Click the Create button",
                "data": "",
                "expected": "Supplier is created successfully.",
            },
        }
        login_map = {
            "user name": {
                "action": "Log into Oracle",
                "navigation": "Enter User Name in the User Name field",
                "data": "User Name: valid_user",
                "expected": "Username is captured.",
            },
            "password": {
                "action": "Log into Oracle",
                "navigation": "Enter Password in the Password field",
                "data": "Password: valid_password",
                "expected": "Password is captured.",
            },
            "sign in": {
                "action": "Log into Oracle",
                "navigation": "Click the Sign In button",
                "data": "",
                "expected": "Credentials are submitted.",
            },
            "enter passcode": {
                "action": "Log into Oracle",
                "navigation": "Enter the MFA Passcode",
                "data": "Enter passcode received via MFA",
                "expected": "Passcode is captured.",
            },
            "verify": {
                "action": "Log into Oracle",
                "navigation": "Click the Verify button",
                "data": "",
                "expected": "MFA verification completes successfully.",
            },
        }

        for detail in manual_steps:
            label = str(detail.get("label") or "").strip()
            key = label.lower()
            current = detail.copy()

            if key == "procurement" and not navigator_added:
                refined.append(
                    {
                        "action": nav_map["navigator"]["action"],
                        "navigation": nav_map["navigator"]["navigation"],
                        "data": nav_map["navigator"]["data"],
                        "expected": nav_map["navigator"]["expected"],
                        "label": "Navigator",
                    }
                )
                navigator_added = True

            if key in nav_map:
                mapping = nav_map[key]
                current.update(mapping)
                refined.append(current)
                continue

            if key in data_map:
                mapping = data_map[key]
                current.update(mapping)
                refined.append(current)
                if key == "create":
                    refined.append(
                        {
                            "action": "",
                            "navigation": "",
                            "data": "",
                            "expected": "Supplier is created successfully and appears in the supplier list.",
                            "label": "create-result",
                        }
                    )
                continue

            if key in login_map:
                mapping = login_map[key]
                current.update(mapping)
                refined.append(current)
                continue

            refined.append(current)

        return refined

    # def _generate_from_template(self, story: str):
    #     """Fill test cases using the selected template."""
    #     lines = [line.strip() for line in story.splitlines() if line.strip()]
    #     test_cases = []

    #     if "rows" in self.template:
    #         # Excel/CSV style template
    #         for idx, row in enumerate(self.template["rows"], 1):
    #             test_cases.append({"id": idx, **row})
    #     else:
    #         # Format string style (JSON/YAML/TXT)
    #         for idx, line in enumerate(lines, 1):
    #             format_str = self.template.get("format", "{title}")
    #             fields = self.template.get("fields", ["title"])

    #             filled = format_str
    #             for field in fields:
    #                 value = line if field == "title" else f"<{field}_value>"
    #                 filled = filled.replace(f"{{{field}}}", value)

    #             test_cases.append({"id": idx, "test_case": filled})

    #     return test_cases
    
def map_llm_to_template(llm_output, template_df):
    """Map LLM output into the structure of the uploaded Excel template.
    - If the template looks like the detailed-flow sheet (SL/Action/Navigation Steps/Key Data Element Examples/Expected Results),
      delegate to the detailed mapper to emit one row per manual step.
    - Otherwise, populate generic columns (ID/Title/Type/Preconditions/Steps/Data/Expected/Priority/Tags/Assumptions) as available.
    """
    # Columns from the uploaded template
    columns = list(template_df.columns) if hasattr(template_df, "columns") else []
    normalized_columns = [str(c).strip().lower() for c in columns]

    # Detailed-flow template detection
    required = {"sl", "action", "navigation steps", "key data element examples", "expected results"}
    if required.issubset(set(normalized_columns)):
        return _map_to_detailed_flow_template(llm_output, template_df, columns, normalized_columns)

    def join_numbered(items: List[str]) -> str:
        return "\n".join(f"{idx}. {str(value)}" for idx, value in enumerate(items, start=1) if str(value).strip())

    def format_dict(data_dict: dict) -> str:
        if not data_dict:
            return ""
        lines = []
        for key, value in data_dict.items():
            formatted_value = value
            if isinstance(value, (dict, list)):
                formatted_value = json.dumps(value, ensure_ascii=False)
            lines.append(f"{key}: {formatted_value}")
        return "\n".join(lines)

    def flatten_step_strings(case: dict) -> List[str]:
        details = case.get("step_details") or []
        if isinstance(details, list) and details and isinstance(details[0], dict):
            strings = []
            for d in details:
                action = d.get("action", "")
                navigation = d.get("navigation", "")
                combined = " - ".join([p for p in [action, navigation] if p]).strip(" -") or navigation or action
                if d.get("data"):
                    combined = f"{combined} | Data: {d['data']}" if combined else f"Data: {d['data']}"
                if d.get("expected"):
                    combined = f"{combined} | Expected: {d['expected']}" if combined else f"Expected: {d['expected']}"
                if combined:
                    strings.append(combined)
            return strings
        # Fallback: use plain steps if present
        steps = case.get("steps") or []
        return [str(s) for s in steps] if isinstance(steps, list) else [str(steps)]

    rows: List[dict] = []
    if not columns:
        # No template columns; fall back to a default structure
        default_rows = [
            {
                "ID": case.get("id", ""),
                "Title": case.get("title", ""),
                "Type": case.get("type", ""),
                "Preconditions": join_numbered(case.get("preconditions", [])),
                "Steps": join_numbered(flatten_step_strings(case)),
                "Data": format_dict(case.get("data", {})),
                "Expected": case.get("expected", ""),
                "Priority": case.get("priority", ""),
                "Tags": ", ".join(case.get("tags", []) or []),
                "Assumptions": "\n".join(case.get("assumptions", []) or []),
            }
            for case in llm_output
        ]
        columns = list(default_rows[0].keys()) if default_rows else []
        return pd.DataFrame(default_rows, columns=columns)

    # Generic mapping into provided template columns
    for case in llm_output:
        row = {}
        for col, norm in zip(columns, normalized_columns):
            if "id" in norm and "grid" not in norm:
                row[col] = case.get("id", "")
            elif any(k in norm for k in ["title", "scenario", "objective"]):
                row[col] = case.get("title", "")
            elif "type" in norm or "case type" in norm:
                row[col] = case.get("type", "")
            elif any(k in norm for k in ["precondition", "prerequisite"]):
                row[col] = join_numbered(case.get("preconditions", []) or [])
            elif "step" in norm:
                row[col] = join_numbered(flatten_step_strings(case))
            elif any(k in norm for k in ["expected", "result"]):
                row[col] = case.get("expected", "")
            elif "data" in norm:
                row[col] = format_dict(case.get("data", {}) or {})
            elif "priority" in norm:
                row[col] = case.get("priority", "")
            elif "tag" in norm:
                row[col] = ", ".join(case.get("tags", []) or [])
            elif any(k in norm for k in ["assumption", "note"]):
                row[col] = "\n".join(case.get("assumptions", []) or [])
            else:
                row[col] = ""
        rows.append(row)

    return pd.DataFrame(rows, columns=columns)


def _derive_manual_action(detail: dict, default_action: str, previous_action: str) -> str:
    navigation_raw = str(detail.get("navigation", "")).strip()
    action_hint_raw = str(detail.get("action", "")).strip()
    navigation = navigation_raw.lower()
    action_hint = action_hint_raw.lower()
    if action_hint_raw:
        return action_hint_raw
    if any(v in navigation for v in ["navigate", "open", "go to"]):
        return "Navigate"
    if any(v in navigation for v in ["enter", "fill", "type", "select", "choose", "pick", "click", "press", "submit", "save", "toggle", "verify", "confirm"]):
        return previous_action or default_action
    if "end of task" in navigation:
        return "End of Task"
    return previous_action or default_action


def _map_to_detailed_flow_template(llm_output, template_df, columns, normalized_columns):
    df_columns = list(columns)
    column_map = {norm: original for norm, original in zip(normalized_columns, df_columns)}

    sl_col = column_map["sl"]
    action_col = column_map["action"]
    nav_col = column_map["navigation steps"]
    data_col = column_map["key data element examples"]
    expected_col = column_map["expected results"]

    expected_keywords = [
        "expected", "displayed", "visible", "shown", "saved", "success",
        "error", "warning", "message", "confirmation", "appears",
        "opens", "launched", "result", "validated"
    ]

    rows = []
    sl_counter = 1
    last_action_written = None

    def normalise_expected(text: str) -> str:
        text = text.strip()
        if not text:
            return ""
        return text

    def has_expected_text(text: str) -> bool:
        lower = text.lower()
        return any(keyword in lower for keyword in expected_keywords) or "should" in lower or lower.startswith("expected")

    for case in llm_output:
        raw_details = case.get("step_details")
        if raw_details and isinstance(raw_details, list) and raw_details and isinstance(raw_details[0], dict):
            details_iterable = raw_details
        else:
            raw_steps = case.get("steps", [])
            if isinstance(raw_steps, str):
                raw_steps = [s.strip() for s in raw_steps.split("\n") if s.strip()]
            details_iterable = [{"action": "", "navigation": str(step), "data": "", "expected": ""} for step in raw_steps]

        details_iterable = [
            detail for detail in details_iterable
            if detail and (detail.get("navigation") or detail.get("data") or detail.get("expected") or detail.get("action"))
        ]
        if not details_iterable:
            continue

        case_title = str(case.get("title") or "").strip() or "Scenario"
        rows.append({
            sl_col: "",
            action_col: case_title,
            nav_col: "",
            data_col: "",
            expected_col: "",
        })

        default_action = case_title
        previous_action = ""
        case_expected = normalise_expected(case.get("expected", ""))
        last_action_written = None

        # Do not insert a Title row; start directly with actionable steps

        for detail in details_iterable:
            action_value = _derive_manual_action(detail, default_action, previous_action)
            navigation_value = str(detail.get("navigation", "")).strip()
            data_value = str(detail.get("data", "")).strip()
            expected_value = normalise_expected(str(detail.get("expected", "")).strip())

            if not navigation_value and has_expected_text(expected_value):
                navigation_value = ""

            if not expected_value and has_expected_text(navigation_value):
                expected_value = navigation_value
                navigation_value = ""

            display_action = action_value
            if last_action_written is not None and action_value == last_action_written:
                display_action = ""
            else:
                last_action_written = action_value

            rows.append({
                sl_col: sl_counter,
                action_col: display_action,
                nav_col: navigation_value,
                data_col: data_value,
                expected_col: expected_value,
            })

            previous_action = action_value
            sl_counter += 1

        if case_expected:
            rows.append({
                sl_col: sl_counter,
                action_col: previous_action or default_action,
                nav_col: "",
                data_col: "",
                expected_col: case_expected,
            })
            sl_counter += 1

        # Append only 'End of Task' as the final line (no trailing Title)
        rows.append({
            sl_col: sl_counter,
            action_col: "End of Task",
            nav_col: "",
            data_col: "",
            expected_col: "",
        })
        sl_counter += 1

    if not rows:
        return template_df.copy()

    def _append_field(accumulator: dict, column: str, new_value: str):
        if not column:
            return
        value = str(new_value or "").strip()
        if not value:
            return
        existing = str(accumulator.get(column) or "").strip()
        if existing:
            accumulator[column] = f"{existing}\n{value}"
        else:
            accumulator[column] = value

    merged_rows: List[dict] = []
    for row in rows:
        action_value = str(row.get(action_col) or "").strip()
        if action_value:
            merged_rows.append(row)
            continue
        if not merged_rows:
            merged_rows.append(row)
            continue
        target = merged_rows[-1]
        prefix = str(row.get(sl_col) or "").strip()
        nav_text = str(row.get(nav_col) or "").strip()
        data_text = str(row.get(data_col) or "").strip()
        expected_text = str(row.get(expected_col) or "").strip()

        def _with_prefix(text: str) -> str:
            stripped = text.strip()
            if not stripped:
                return stripped
            return f"{prefix}. {stripped}" if prefix else stripped

        if nav_text:
            _append_field(target, nav_col, _with_prefix(nav_text))
        if data_text:
            _append_field(target, data_col, _with_prefix(data_text))
        if expected_text:
            _append_field(target, expected_col, _with_prefix(expected_text))

    # Normalize SL column to keep sequential numbering after merges
    current_sl = 0
    for row in merged_rows:
        if isinstance(row.get(sl_col), int):
            current_sl = row[sl_col]
        elif str(row.get(sl_col) or "").isdigit():
            current_sl = int(row[sl_col])
        else:
            current_sl += 1
            row[sl_col] = current_sl

    return pd.DataFrame(merged_rows, columns=df_columns)


def export_to_excel(mapped_df, output_path="generated_test_cases.xlsx"):
    """Save the mapped DataFrame to an Excel file."""
    mapped_df.to_excel(output_path, index=False)
    return output_path
