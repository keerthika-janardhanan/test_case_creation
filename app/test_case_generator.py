import os
import json
import re
import ast
import copy
import logging
from pathlib import Path
from typing import List, Tuple, Optional

import pandas as pd
from vector_db import VectorDBClient
from langchain_openai import AzureChatOpenAI
from recorder_enricher import slugify, GENERATED_DIR
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
            context_chunks, flow_steps, context_sources = self._collect_context(story)
        except re.error as exc:
            pattern = getattr(exc, "pattern", None)
            raise ValueError(
                f"Regex failure while collecting context (pattern={pattern!r}): {exc}"
            ) from exc
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
        return cases

    def _agentic_generate(self, story: str, context_text: str, flow_steps: List[dict], context_sources: List[str], max_attempts: int = 2, llm_only: bool = False) -> List[dict]:
        last_error = ""
        flow_steps_prompt_json = self._flow_steps_prompt_json(flow_steps)
        for attempt in range(1, max_attempts + 1):
            prompt = self._build_generation_prompt(
                story,
                context_text,
                flow_steps_prompt_json,
            )
            if attempt > 1:
                strict_suffix = (
                    "\n\nIMPORTANT: Your previous output failed validation. Return ONLY a valid JSON array with objects containing keys "
                    f"{', '.join(self.default_fields)} and 'step_details'. No prose, no code fences, no trailing commas, no comments."
                )
                prompt = prompt + strict_suffix

            try:
                resp = self.llm.invoke(prompt)
            except re.error as exc:
                pattern = getattr(exc, "pattern", None)
                raise ValueError(
                    f"Regex failure while invoking LLM (pattern={pattern!r}): {exc}"
                ) from exc

            output = resp.content if hasattr(resp, "content") else str(resp)
            # Strip fences
            try:
                output = re.sub(r"^```(?:json)?\s*", "", output, flags=re.DOTALL)
                output = re.sub(r"\s*```$", "", output, flags=re.DOTALL).strip()
            except re.error as exc:
                pattern = getattr(exc, "pattern", None)
                raise ValueError(
                    f"Regex failure while sanitising LLM output (pattern={pattern!r}): {exc}"
                ) from exc
            output = output.strip()

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
            except json.JSONDecodeError as je:
                last_error = f"json decode: {je}"
                repaired = self._repair_llm_output_to_json_array(normalized_output)
                if isinstance(repaired, list):
                    parsed_cases = repaired

            if isinstance(parsed_cases, list):
                cleaned = self._enforce_schema(parsed_cases)
                # Optionally bypass deterministic injection to rely solely on LLM output
                if not llm_only:
                    cleaned = self._inject_flow_details(cleaned, flow_steps, context_sources)
                if cleaned:
                    return cleaned
                last_error = "parsed but no valid cases after schema enforcement"

        # All attempts failed; choose fallback strategy
        if flow_steps and not llm_only:
            return self._fallback_from_flow(story, flow_steps)
        # Synthesize from vector context
        return self._synthesize_from_context(story, context_text, context_sources)

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
        flow_slug = slugify(story)
        candidates = [
            {"query": story, "where": {"type": "recorder_refined", "flow_slug": flow_slug}},
            {"query": flow_slug, "where": {"type": "recorder_refined", "flow_slug": flow_slug}},
            {"query": story, "where": {"type": "recorder_refined", "flow_name": story}},
        ]
        steps_map: dict[int, dict] = {}
        element_map: dict[int, dict] = {}
        for spec in candidates:
            try:
                results = self.db.query_where(spec["query"], spec["where"], top_k=top_k)
            except Exception as exc:
                logger.debug("Vector query failed (%s): %s", spec["where"], exc)
                continue
            for entry in results or []:
                meta = entry.get("metadata") or {}
                content = self._decode_vector_content(entry.get("content"))
                record_kind = meta.get("record_kind") or content.get("record_kind")
                if record_kind == "element":
                    elem_index = content.get("element_index") or meta.get("element_index")
                    try:
                        elem_index = int(elem_index)
                    except (TypeError, ValueError):
                        elem_index = len(element_map) + 1
                    label = (content.get("label") or meta.get("label") or "").strip()
                    if not label:
                        continue
                    role = (content.get("role") or meta.get("role") or "").strip()
                    tag = (content.get("tag") or meta.get("tag") or "").strip()
                    locator_block = content.get("locators") or {}
                    locators = locator_block if isinstance(locator_block, dict) else {}
                    if not locators or "playwright" not in locators:
                        if role and label:
                            locators = {"playwright": {"byRole": {"role": role, "name": label}}}
                        else:
                            locators = {"playwright": {"byText": label}}
                    element_map[elem_index] = {
                        "step": elem_index,
                        "action": label,
                        "navigation": "",
                        "data": "",
                        "expected": "",
                        "locators": {
                            **locators,
                            "labels": label,
                            "role": role,
                            "tag": tag,
                            "name": label,
                        },
                    }
                    continue

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
                existing = steps_map.get(step_index)
                if existing and existing.get("locators") and not locators:
                    continue
                steps_map[step_index] = {
                    "step": step_index,
                    "action": action,
                    "navigation": navigation,
                    "data": data_val,
                    "expected": expected,
                    "locators": locators,
                }
            if element_map or steps_map:
                break

        if element_map:
            ordered_steps = [element_map[idx] for idx in sorted(element_map)]
            snippet_lines = [f"Element {item.get('step')}: {item.get('action')}" for item in ordered_steps[:12]]
            summary = f"Vector flow (elements): {story}\n" + "\n".join(snippet_lines)
            return [summary], ordered_steps

        if not steps_map:
            return [], []

        ordered_steps = [steps_map[idx] for idx in sorted(steps_map)]
        snippet_lines = []
        for item in ordered_steps[:12]:
            descriptor = item.get("action") or item.get("navigation") or ""
            snippet_lines.append(f"Step {item.get('step')}: {descriptor}")

        summary = f"Vector flow: {story}\n" + "\n".join(snippet_lines)
        return [summary], ordered_steps

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
            dedupe_key = (role, label.lower(), tag, navigation)
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
            dedupe_key = (role, label.lower(), tag, "")
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
        for idx, step in enumerate(flow_steps, start=1):
            locators = step.get("locators") if isinstance(step, dict) else {}
            label_value: str = ""
            role_value: str = ""
            locator_hint: str = ""
            if isinstance(locators, dict):
                labels_field = locators.get("labels")
                if isinstance(labels_field, (list, tuple, set)):
                    label_value = ", ".join(str(part).strip() for part in labels_field if part)
                elif labels_field:
                    label_value = str(labels_field).strip()
                if not label_value and locators.get("playwright"):
                    label_value = str(locators.get("playwright")).strip()
                role_value = str(locators.get("role") or "").strip()
                locator_hint = str(locators.get("playwright") or "").strip()
                if not role_value and locator_hint:
                    match = re.search(r"getByRole\(\s*['\"]([^'\"]+)['\"]", locator_hint)
                    if match:
                        role_value = match.group(1)
            if not label_value:
                label_value = str(step.get("navigation") or step.get("action") or "").strip()

            summary.append(
                {
                    "step": idx,
                    "action": step.get("action"),
                    "label": label_value,
                    "role": role_value,
                    "locator": locator_hint,
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

    def _build_generation_prompt(self, story: str, context: str, flow_steps_json: str) -> str:
        fields = ", ".join(self.default_fields)
        return (
            "You are an expert QA engineer for Oracle Fusion / enterprise web flows.\n"
            "Using ONLY the retrieved context, derive comprehensive, professional manual test cases covering positive, negative, and edge scenarios.\n"
            f"The user supplied keywords or artifact name: '{story}'.\n"
            "Context snippets (prioritise Playwright flows, repo scaffolds, Jira docs):\n"
            f"{context}\n\n"
            "You are also provided recorder element cues per step. Each item contains: the recorder step index, the intended action verb, the captured UI label(s), the ARIA role (if available), and the original Playwright locator snippet.\n"
            "For the primary positive scenario, mirror these steps in order, deriving navigation wording directly from the element labels and role context (do not invent new UI names). Expand the labels into detailed actions with explicit navigation, data entry, and observable expected outcomes.\n"
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

    def generate_manual_table(self, story: str, db_query: Optional[str] = None, scope: Optional[str] = None) -> str:
        """Generate a markdown table using the dedicated manual-table prompt. Returns raw markdown text."""
        context_chunks, flow_steps, _ = self._collect_context(story)
        manual_steps: List[dict] = []
        if flow_steps:
            if any(isinstance(step, dict) and (step.get("locators") or {}).get("playwright") for step in flow_steps):
                manual_steps = self._build_manual_steps_from_refined(flow_steps)
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
            manual_steps = self._refine_manual_steps_phrasing(manual_steps)
            return self._manual_steps_to_markdown(manual_steps)

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
    def _build_manual_steps_from_refined(self, refined_steps: List[dict]) -> List[dict]:
        """Build manual steps from refined Playwright cues in a generic, data-driven way.
        Rules:
        - Use only Playwright getByRole/getByText/getByLabel cues; ignore raw CSS/XPath.
        - Do not hardcode domain values or flow-specific text; derive labels from the cues.
        - Generate generic navigation/data/expected phrasing based on the role and label text.
        - Skip anonymous svg/img/path/a elements with no label.
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

            if not nav_text and label:
                nav_text = f"Click on {quoted}"

            if not nav_text:
                continue

            dedupe_key = (
                (role or "").lower(),
                label.lower() if label else "",
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

    def _generate_from_template(self, story: str):
        """Fill test cases using the selected template."""
        lines = [line.strip() for line in story.splitlines() if line.strip()]
        test_cases = []

        if "rows" in self.template:
            # Excel/CSV style template
            for idx, row in enumerate(self.template["rows"], 1):
                test_cases.append({"id": idx, **row})
        else:
            # Format string style (JSON/YAML/TXT)
            for idx, line in enumerate(lines, 1):
                format_str = self.template.get("format", "{title}")
                fields = self.template.get("fields", ["title"])

                filled = format_str
                for field in fields:
                    value = line if field == "title" else f"<{field}_value>"
                    filled = filled.replace(f"{{{field}}}", value)

                test_cases.append({"id": idx, "test_case": filled})

        return test_cases
    
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

    return pd.DataFrame(rows, columns=df_columns)


def export_to_excel(mapped_df, output_path="generated_test_cases.xlsx"):
    """Save the mapped DataFrame to an Excel file."""
    mapped_df.to_excel(output_path, index=False)
    return output_path
