import os
import json
import re
import ast
from pathlib import Path
from typing import List, Tuple, Optional

import pandas as pd
from vector_db import VectorDBClient
from langchain_openai import AzureChatOpenAI
from recorder_enricher import slugify, GENERATED_DIR

SECTION_KEYWORDS = [
    ("login", "Log into Oracle"),
    ("sign in", "Log into Oracle"),
    ("navigator", "Navigate"),
    ("supplier", "Create a Supplier"),
    ("create supplier", "Create a Supplier"),
    ("address", "Addresses"),
    ("transaction tax", "Transaction Tax"),
    ("site", "Sites"),
    ("contact", "Contacts"),
    ("end of task", "End of Task"),
]

SELECTOR_HINTS = {
    "navigator": " (top-left Navigator menu)",
    "task pane": " (sheet-of-paper icon on the right)",
    "create supplier": " hyperlink in the Tasks region",
    "addresses": " tab",
    "transaction tax": " sub tab",
    "receiving": " sub tab",
    "purchasing": " sub tab",
    "invoicing": " sub tab",
    "site assignments": " sub tab",
    "save and close": " button",
}

EXPECTED_HINTS = {
    "navigator": "Navigator menu opens.",
    "create supplier": "The Create Supplier pop up window is visible.",
    "task pane": "The Task Pane is displayed.",
    "addresses": "The Addresses tab is displayed.",
    "transaction tax": "The Transaction Tax work area is displayed.",
    "sites": "The Sites work area is displayed.",
    "contacts": "The Contacts tab is displayed.",
    "save and close": "A confirmation window is displayed.",
}

ROLE_PATTERN = re.compile(r"getByRole\(\s*['\"]([^'\"]+)['\"]")
NAME_PATTERN = re.compile(r"name\s*:\s*['\"]([^'\"]+)['\"]")
LABEL_PATTERN = re.compile(r"getByLabel\(\s*['\"]([^'\"]+)['\"]")
TEXT_PATTERN = re.compile(r"getByText\(\s*['\"]([^'\"]+)['\"]")
PLACEHOLDER_PATTERN = re.compile(r"getByPlaceholder\(\s*['\"]([^'\"]+)['\"]")
LOCATOR_TEXT_PATTERN = re.compile(r"text=([^\"'\)]+)")
DATA_TESTID_PATTERN = re.compile(r"data-testid['\"]?\s*[:=]\s*['\"]([^'\"]+)['\"]")


class TemplateLoader:
    """Utility to load test case templates from different formats."""

    @staticmethod
    def load_template(file_path: str):
        ext = os.path.splitext(file_path)[1].lower()

        if ext == ".json":
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)

        elif ext in (".yaml", ".yml"):
            import yaml
            with open(file_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)

        elif ext in (".txt", ".md"):
            with open(file_path, "r", encoding="utf-8") as f:
                return {"format": f.read(), "fields": []}

        elif ext in (".csv", ".xlsx"):
            df = pd.read_excel(file_path) if ext == ".xlsx" else pd.read_csv(file_path)
            return {
                "fields": list(df.columns),
                "rows": df.to_dict(orient="records"),
                "format": None,
            }

        else:
            raise ValueError(f"Unsupported template file type: {ext}")


class TestCaseGenerator:
    def __init__(self, db: VectorDBClient, template=None, llm: Optional[object] = None):
        self.db = db
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

        # ✅ Use AzureChatOpenAI instead of ChatOpenAI (allow injection for testing)
        self.llm = llm or AzureChatOpenAI(
            openai_api_version=os.getenv("OPENAI_API_VERSION"),
            azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT", "GPT-4o"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_key=os.getenv("AZURE_OPENAI_KEY"),
            temperature=0.2,
        )

    def generate_test_cases(self, story: str, per_step_negatives: int = 1, per_step_edges: int = 1, max_steps_for_variants: int = 8):
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
        cases = self._agentic_generate(story, context_text, flow_steps, context_sources)
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

    def _agentic_generate(self, story: str, context_text: str, flow_steps: List[dict], context_sources: List[str], max_attempts: int = 2) -> List[dict]:
        last_error = ""
        for attempt in range(1, max_attempts + 1):
            prompt = self._build_generation_prompt(
                story,
                context_text,
                json.dumps(flow_steps, ensure_ascii=False) if flow_steps else "[]",
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
                cleaned = self._inject_flow_details(cleaned, flow_steps, context_sources)
                if cleaned:
                    return cleaned
                last_error = "parsed but no valid cases after schema enforcement"

        # All attempts failed; choose fallback strategy
        if flow_steps:
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

    def _collect_context(self, story: str, top_k: int = 8) -> Tuple[List[str], List[dict], List[str]]:
        chunks: List[str] = []
        matched_flow_steps: List[dict] = []
        context_sources: List[str] = []
        seen_ids = set()
        queries = [story]
        tokens = [tok for tok in re.split(r"[^a-zA-Z0-9]+", story) if tok and len(tok) >= 3]
        for tok in tokens:
            if tok.lower() not in {q.lower() for q in queries}:
                queries.append(tok)

        for term in queries:
            if not term:
                continue
            results = self.db.query(term, top_k=top_k)
            for entry in results:
                is_dict = isinstance(entry, dict)
                entry_id = entry.get("id") if is_dict else str(entry)
                if entry_id in seen_ids:
                    continue
                seen_ids.add(entry_id)
                metadata = entry.get("metadata", {}) if is_dict else {}
                artifact_type = str(metadata.get("artifact_type") or metadata.get("type") or "").lower()
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
                chunks.append(
                    f"Source: {source_label} | Descriptor: {descriptor_label}\n{snippet}"
                )
                context_sources.append(f"{source_label}:{descriptor_label}")
                if len(chunks) >= top_k:
                    break
            if len(chunks) >= top_k:
                break

        flow_chunks, flow_steps = self._load_saved_flows(story)
        chunks.extend(flow_chunks)
        if flow_steps:
            matched_flow_steps = flow_steps
            for item in flow_steps[:3]:
                context_sources.append(f"recorder:{item.get('navigation') or item.get('action')}")

        return chunks, matched_flow_steps, context_sources

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

        # Fallback: if nothing matched, take first few most recent flows
        if not matched_any:
            for path in flow_files[:limit]:
                try:
                    raw = path.read_text(encoding="utf-8")
                    data = json.loads(raw)
                except Exception:
                    continue
                flow_title = str(data.get("flow_name") or "")
                steps = data.get("steps") or []
                humanized = build_humanized(path, flow_title, steps)
                if humanized and not structured_steps:
                    structured_steps = humanized
                if len(snippets) >= limit:
                    break

        return snippets, structured_steps

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

    def _build_generation_prompt(self, story: str, context: str, flow_steps_json: str) -> str:
        fields = ", ".join(self.default_fields)
        return (
            "You are an expert QA engineer for Oracle Fusion / enterprise web flows.\n"
            "Using ONLY the retrieved context, derive comprehensive, professional manual test cases covering positive, negative, and edge scenarios.\n"
            f"The user supplied keywords or artifact name: '{story}'.\n"
            "Context snippets (prioritise Playwright flows, repo scaffolds, Jira docs):\n"
            f"{context}\n\n"
            "You are also provided the recorder flow steps (each item has step index, action, navigation description, data hints, expected hints). "
            "For the primary positive scenario, you MUST mirror these steps exactly, expanding them into detailed test actions with explicit navigation, data entry, and observable expected outcomes.\n"
            f"Recorder flow steps JSON:\n{flow_steps_json}\n\n"
            "Additionally, for EACH core step in the positive flow (up to 6-8 main steps), generate at least one negative and one edge case focusing on that step's validation (e.g., required field empty, invalid format, unauthorized action, boundary values). Keep these as separate cases with precise 'type' values and step-by-step actions.\n\n"
            "Output strictly as a JSON array. Respond with ONLY the JSON array — no prose, no explanations, no code fences. Each element must contain the fields: "
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
    """
    Map LLM output into the structure of the uploaded Excel template.
    Each generated test case becomes a new row that follows template headers.
    """
    def join_numbered(items):
        return "\n".join(f"{idx}. {str(value)}" for idx, value in enumerate(items, start=1) if str(value).strip())

    def format_dict(data_dict):
        if not data_dict:
            return ""
        lines = []
        for key, value in data_dict.items():
            formatted_value = value
            if isinstance(value, (dict, list)):
                formatted_value = json.dumps(value, ensure_ascii=False)
            lines.append(f"{key}: {formatted_value}")
        return "\n".join(lines)

    def flatten_step_strings(case):
        details = case.get("step_details") or []
        if details and isinstance(details, list) and details and isinstance(details[0], dict):
            strings = []
            for detail in details:
                action = detail.get("action", "")
                navigation = detail.get("navigation", "")
                combined = " - ".join(filter(None, [action, navigation])).strip()
                combined = combined or navigation or action
                if detail.get("data"):
                    combined = f"{combined} | Data: {detail['data']}" if combined else f"Data: {detail['data']}"
                if detail.get("expected"):
                    combined = f"{combined} | Expected: {detail['expected']}" if combined else f"Expected: {detail['expected']}"
                if combined:
                    strings.append(combined)
            # Insert Title at the top, keep End of Task at the end
            title = str(case.get("title") or "").strip()
            ctype = str(case.get("type") or "").strip().capitalize()
            if title:
                title_line = f"Title: {title} ({ctype})" if ctype else f"Title: {title}"
                strings.insert(0, title_line)
            strings.append("End of Task")
            return strings
        return case.get("steps", [])

    rows = []
    columns = list(template_df.columns)

    normalized_columns = [col.lower().strip() for col in columns]
    detailed_flow_cols = {"sl", "action", "navigation steps", "key data element examples", "expected results"}

    if detailed_flow_cols.issubset(set(normalized_columns)):
        return _map_to_detailed_flow_template(llm_output, template_df, columns, normalized_columns)

    for case in llm_output:
        row = {}
        for col in columns:
            col_lower = col.lower()

            if "id" in col_lower and "grid" not in col_lower:
                row[col] = case.get("id", "")
            elif "title" in col_lower or "scenario" in col_lower or "objective" in col_lower:
                row[col] = case.get("title", "")
            elif "type" in col_lower or "case type" in col_lower:
                row[col] = case.get("type", "")
            elif "precondition" in col_lower or "prerequisite" in col_lower:
                preconditions = case.get("preconditions", [])
                row[col] = join_numbered(preconditions) if preconditions else ""
            elif "step" in col_lower:
                steps = flatten_step_strings(case)
                row[col] = join_numbered(steps) if steps else ""
            elif "expected" in col_lower or "result" in col_lower:
                row[col] = case.get("expected", "")
            elif "data" in col_lower:
                row[col] = format_dict(case.get("data", {}))
            elif "priority" in col_lower:
                row[col] = case.get("priority", "")
            elif "tag" in col_lower:
                tags = case.get("tags", [])
                row[col] = ", ".join(tags) if tags else ""
            elif "assumption" in col_lower or "note" in col_lower:
                assumptions = case.get("assumptions", [])
                row[col] = "\n".join(assumptions) if assumptions else ""
            else:
                row[col] = ""

        rows.append(row)

    # If template had no columns, fall back to default structure
    if not columns:
        rows = [
            {
                "ID": case.get("id", ""),
                "Title": case.get("title", ""),
                "Type": case.get("type", ""),
                "Preconditions": join_numbered(case.get("preconditions", [])),
                "Steps": join_numbered(flatten_step_strings(case)),
                "Data": format_dict(case.get("data", {})),
                "Expected": case.get("expected", ""),
                "Priority": case.get("priority", ""),
                "Tags": ", ".join(case.get("tags", [])),
                "Assumptions": "\n".join(case.get("assumptions", [])),
            }
            for case in llm_output
        ]
        columns = list(rows[0].keys()) if rows else []

    return pd.DataFrame(rows, columns=columns)


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

    def derive_action(detail, default_action, previous_action):
        navigation_raw = str(detail.get("navigation", "")).strip()
        action_hint_raw = str(detail.get("action", "")).strip()
        navigation = navigation_raw.lower()
        action_hint = action_hint_raw.lower()
        combined = action_hint or navigation
        if any(token in combined for token in ["log in", "log into", "sign in", "login"]):
            return "Log into Oracle"
        if "navigator" in combined or "navigate" in combined:
            return "Navigate"
        if "supplier" in combined and "create" in combined:
            return "Create Supplier"
        if "address" in combined:
            return "Addresses"
        if "transaction tax" in combined:
            return "Transaction Tax"
        if "site" in combined:
            return "Sites"
        if "contact" in combined:
            return "Contacts"
        if "end of task" in combined or "complete" in combined:
            return "End of Task"
        if action_hint_raw:
            return action_hint_raw
        if previous_action:
            return previous_action
        return default_action

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

        default_action = case.get("title", "Scenario")
        previous_action = ""
        case_expected = normalise_expected(case.get("expected", ""))
        last_action_written = None

        # Prepend Title row
        title = str(case.get("title") or "").strip()
        ctype = str(case.get("type") or "").strip().capitalize()
        label = f"Title: {title} ({ctype})" if title and ctype else (f"Title: {title}" if title else "")
        if label:
            rows.append({
                sl_col: sl_counter,
                action_col: label,
                nav_col: "",
                data_col: "",
                expected_col: "",
            })
            sl_counter += 1

        for detail in details_iterable:
            action_value = derive_action(detail, default_action, previous_action)
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
