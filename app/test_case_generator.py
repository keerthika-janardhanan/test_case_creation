import os
import json
import re
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
    def __init__(self, db: VectorDBClient, template=None):
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

        # ✅ Use AzureChatOpenAI instead of ChatOpenAI
        self.llm = AzureChatOpenAI(
            openai_api_version=os.getenv("OPENAI_API_VERSION"),
            azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT", "GPT-4o"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_key=os.getenv("AZURE_OPENAI_KEY"),
            temperature=0.2,
        )

    def generate_test_cases(self, story: str):
        try:
            context_chunks, flow_steps, context_sources = self._collect_context(story)
        except re.error as exc:
            pattern = getattr(exc, "pattern", None)
            raise ValueError(
                f"Regex failure while collecting context (pattern={pattern!r}): {exc}"
            ) from exc
        self.cached_flow_steps = flow_steps
        context_text = "\n\n---\n".join(context_chunks) if context_chunks else "(No direct context retrieved. Provide best-effort scenarios and state assumptions.)"

        prompt_text = self._build_generation_prompt(
            story,
            context_text,
            json.dumps(flow_steps, ensure_ascii=False) if flow_steps else "[]",
        )

        try:
            resp = self.llm.invoke(prompt_text)
        except re.error as exc:
            pattern = getattr(exc, "pattern", None)
            raise ValueError(
                f"Regex failure while invoking LLM (pattern={pattern!r}): {exc}"
            ) from exc

        output = resp.content if hasattr(resp, "content") else str(resp)

        # Remove code fences if any
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

        try:
            test_cases = json.loads(normalized_output)
        except json.JSONDecodeError as e:
            preview = normalized_output[:800] + ("..." if len(normalized_output) > 800 else "")
            print(f"❌ JSON parse error while generating test cases: {e}\nOutput snippet:\n{preview}")
            raise ValueError("Generated test cases were not valid JSON. Please retry or adjust keywords.") from e

        cleaned_cases = self._enforce_schema(test_cases)
        cleaned_cases = self._inject_flow_details(cleaned_cases, flow_steps, context_sources)
        if not cleaned_cases:
            raise ValueError("No valid test cases could be generated from the provided context.")
        return cleaned_cases

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

        key = re.sub(r"[^a-zA-Z0-9]", "", story.lower())
        snippets = []
        structured_steps: List[dict] = []

        def process_flow(path: Path) -> Optional[List[dict]]:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                return None
            steps = data.get("steps") or []
            enriched = self._load_enriched_steps(path.stem)
            humanized = enriched if enriched else self._humanize_flow_steps(steps, path.stem)
            if not humanized:
                return None
            step_lines = []
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

        for path in flows_dir.glob("*.json"):
            stem = path.stem.lower()
            if key and key not in re.sub(r"[^a-zA-Z0-9]", "", stem):
                continue
            humanized = process_flow(path)
            if humanized and not structured_steps:
                structured_steps = humanized
            if len(snippets) >= limit:
                break

        if not snippets:
            for path in list(flows_dir.glob("*.json"))[:limit]:
                humanized = process_flow(path)
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
            "Output strictly as a JSON array. Each element must contain the fields: "
            f"{fields}, plus an additional field 'step_details'.\n"
            "'step_details' must be an ordered list of objects with keys:\n"
            "- action: High-level activity label (e.g., 'Log into Oracle', 'Navigate to Payables', 'Create Supplier').\n"
            "- navigation: Exact UI navigation or click sequence (string; multiple lines allowed using \\n).\n"
            "- data: Key data inputs for that step (string summarising field-value pairs; empty string if none).\n"
            "- expected: Immediate system response/validation (string; empty string if none).\n\n"
            "Rules:\n"
            "- Treat each test case as a manual QA script suitable for handover to a test team.\n"
            "- Produce at least one positive, one negative, and one edge case.\n"
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

    if not rows:
        return template_df.copy()

    return pd.DataFrame(rows, columns=df_columns)


def export_to_excel(mapped_df, output_path="generated_test_cases.xlsx"):
    """Save the mapped DataFrame to an Excel file."""
    mapped_df.to_excel(output_path, index=False)
    return output_path
