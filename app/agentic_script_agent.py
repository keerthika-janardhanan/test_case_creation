"""Agentic workflow for generating Playwright test scripts aligned with framework standards."""

from __future__ import annotations

import json
import os
import re
import posixpath
from collections import Counter
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Set
import ast

# Defensive optional imports: keyword-inspect and other non-LLM endpoints should not 500
# just because langchain or langchain-openai isn't installed in a minimal environment.
try:  # pragma: no cover - import guards
    from langchain.prompts import PromptTemplate  # type: ignore
except ImportError:  # Lightweight fallback with compatible .format()
    class PromptTemplate:  # type: ignore
        def __init__(self, input_variables, template: str):
            self.input_variables = input_variables
            self.template = template

        def format(self, **kwargs) -> str:
            return self.template.format(**kwargs)

try:  # pragma: no cover - import guards
    from langchain_openai import AzureChatOpenAI  # type: ignore
except ImportError:
    AzureChatOpenAI = None  # type: ignore

"""Agent responsible for generating previews and deterministic script payloads.

Key reliability adjustments (Oct/Nov 2025):
 - Use package-relative imports so FastAPI app import context doesn't break.
 - Gracefully degrade when Azure OpenAI env vars are missing instead of raising 500.
 - Wrap LLM invocations; return explicit sentinel messages when unavailable.
"""

from .orchestrator import TestScriptOrchestrator
from .git_utils import push_to_git
from .vector_db import VectorDBClient


def _strip_code_fences(text: str) -> str:
    if not text:
        return ""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9_-]*", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"```$", "", cleaned, flags=re.MULTILINE)
    return cleaned.strip()


def _slugify(value: str, default: str = "scenario") -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower())
    value = re.sub(r"-+", "-", value).strip("-")
    return value or default


def _to_camel_case(value: str) -> str:
    if not value:
        return ""
    cleaned = re.sub(r"['\"_]+", " ", str(value))
    cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()
    if not cleaned:
        return ""
    return re.sub(r"[^a-z0-9]+(.)?", lambda m: m.group(1).upper() if m.group(1) else "", cleaned)


def _normalize_selector(selector: str) -> str:
    if not selector:
        return ""
    raw = str(selector).strip()
    hash_index = raw.find("#")
    if hash_index != -1:
        fragment = raw[hash_index + 1 :]
        cut_index = re.search(r'[ \t\r\n>+~,.\[]', fragment)
        if cut_index:
            fragment = fragment[: cut_index.start()]
        fragment = fragment.strip()
        if fragment:
            escaped = fragment.replace('"', r"\"")
            return f'xpath=//*[@id="{escaped}"]'
    normalized = re.sub(r"\|[a-zA-Z][\w-]*", "", raw)
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"\s*([>+~,])\s*", r"\1", normalized)
    normalized = normalized.strip()
    return normalized


def _extract_data_value(step: Dict[str, Any]) -> str:
    data = step.get("data")
    if isinstance(data, str):
        trimmed = data.strip()
        if not trimmed:
            return ""
        if ":" in trimmed:
            key, value = trimmed.split(":", 1)
            return value.strip()
        return trimmed
    return ""


def _extract_data_key(step: Dict[str, Any]) -> str:
    data = step.get("data")
    if isinstance(data, str) and ":" in data:
        key, _ = data.split(":", 1)
        return key.strip()
    navigation = step.get("navigation")
    if isinstance(navigation, str):
        text = navigation.strip()
        match = re.search(r"enter\s+([a-z0-9 _-]+)", text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return ""


def _step_signature(step: Dict[str, Any]) -> str:
    action = (step.get("action") or "").strip().lower()
    navigation = (step.get("navigation") or "").strip().lower()
    data = (step.get("data") or "").strip().lower()
    return f"{action}|{navigation}|{data}"


def _extract_preview_signatures(preview: str) -> Optional[Set[str]]:
    if not preview:
        return None
    signatures: Set[str] = set()
    parsed_count = 0
    for raw_line in preview.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line[0].isdigit():
            parts = line.split(" ", 1)
            if len(parts) == 2:
                line = parts[1].strip()
        if '|' not in line:
            continue
        segments = [segment.strip().lower() for segment in line.split("|")]
        if not segments:
            continue
        action = segments[0]
        navigation = segments[1] if len(segments) > 1 else ""
        data_value = ""
        for segment in segments[2:]:
            if segment.startswith("data:"):
                data_value = segment.split(":", 1)[1].strip()
        signature = f"{action}|{navigation}|{data_value}"
        signatures.add(signature)
        parsed_count += 1
    if parsed_count < 2:
        return None
    return signatures


def _normalize_for_match(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "").strip().lower())
    cleaned = cleaned.replace("'", "").replace('"', "")
    return cleaned


def _extract_preview_phrases(preview: str) -> Set[str]:
    """Collect normalized action/navigation phrases from the preview list.

    The preview format is expected to be pipe-separated columns like:
      Action | Navigation | Data: ... | Expected: ...
    We capture the first two segments (action, navigation) when present; otherwise, we use the whole line.
    """
    phrases: Set[str] = set()
    if not preview:
        return phrases
    for raw_line in preview.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # Strip leading numbering like "19. "
        if line and line[0].isdigit():
            parts = line.split(" ", 1)
            if len(parts) == 2 and parts[0][:-1].isdigit() if parts[0].endswith('.') else parts[0].isdigit():
                line = parts[1].strip()
        if "|" in line:
            segments = [seg.strip() for seg in line.split("|")]
            if segments:
                phrases.add(_normalize_for_match(segments[0]))
            if len(segments) > 1:
                phrases.add(_normalize_for_match(segments[1]))
        else:
            phrases.add(_normalize_for_match(line))
    return {p for p in phrases if p}


def _relative_import(from_path: Path, to_path: Path) -> str:
    rel = os.path.relpath(to_path, start=from_path.parent)
    rel_posix = posixpath.normpath(rel.replace("\\", "/"))
    if not rel_posix.startswith("."):
        rel_posix = f"./{rel_posix}"
    return rel_posix


@dataclass
class FrameworkProfile:
    root: Path
    locators_dir: Optional[Path] = None
    pages_dir: Optional[Path] = None
    tests_dir: Optional[Path] = None
    additional_dirs: Dict[str, Path] = field(default_factory=dict)

    @classmethod
    def from_root(cls, root_path: str | Path) -> "FrameworkProfile":
        root = Path(root_path).expanduser().resolve()
        if not root.exists():
            raise FileNotFoundError(f"Framework repo not found: {root}")

        def find_dir(candidates: List[str]) -> Optional[Path]:
            for name in candidates:
                candidate = root / name
                if candidate.exists() and candidate.is_dir():
                    return candidate
            return None

        locators = find_dir(["locators", "locator", "selectors"])
        pages = find_dir(["pages", "page", "pageObjects", "page_objects", "src/pages"])
        tests = find_dir(["tests", "specs", "test", "e2e", "src/tests"])

        additional = {}
        for name in ["fixtures", "data", "util", "utils", "support"]:
            candidate = root / name
            if candidate.exists() and candidate.is_dir():
                additional[name] = candidate

        return cls(root=root, locators_dir=locators, pages_dir=pages, tests_dir=tests, additional_dirs=additional)

    def sample_snippet(self, directory: Optional[Path], limit_files: int = 2, max_chars: int = 1200) -> str:
        if not directory or not directory.exists():
            return ""

        snippets: List[str] = []
        for path in sorted(directory.glob("**/*.ts"))[:limit_files]:
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            rel = path.relative_to(self.root)
            snippets.append(f"// {rel}\n{content}")
            if sum(len(s) for s in snippets) > max_chars:
                break
        combined = "\n\n".join(snippets)
        return combined[:max_chars]

    def summary(self) -> str:
        parts = [f"Root: {self.root}"]
        if self.locators_dir:
            parts.append(f"Locators dir: {self.locators_dir.relative_to(self.root)}")
        if self.pages_dir:
            parts.append(f"Pages dir: {self.pages_dir.relative_to(self.root)}")
        if self.tests_dir:
            parts.append(f"Tests dir: {self.tests_dir.relative_to(self.root)}")
        if self.additional_dirs:
            parts.append("Additional dirs: " + ", ".join(name for name in self.additional_dirs))
        return " | ".join(parts)


logger = logging.getLogger(__name__)


class AgenticScriptAgent:
    def __init__(self):
        # Lazy-initialize LLM to avoid failures in endpoints that don't require it (e.g., keyword-inspect)
        self.llm = None  # type: ignore[assignment]
        self.orchestrator = TestScriptOrchestrator()
        self.vector_db = VectorDBClient()
        # Initialize prompt templates eagerly so attributes are always present
        self.preview_prompt = PromptTemplate(
            input_variables=[
                "scenario",
                "enriched_steps",
                "existing_script_excerpt",
                "scaffold_snippet",
                "framework_summary",
            ],
            template=(
                "You are an autonomous QA planning agent.\n"
                "STRICT GROUNDING: Only use the 'Contextual steps' provided below.\n"
                "- Do NOT invent steps from prior knowledge or assumptions.\n"
                "- If 'Contextual steps' is empty or clearly unrelated, reply EXACTLY with: INSUFFICIENT_CONTEXT: <one-sentence guidance to record or ingest>.\n"
                "- Otherwise, design a concise, numbered list of Playwright automation steps using only the grounded context.\n"
                "- Respond with Markdown numbered steps only (no prose).\n\n"
                "Scenario:\n{scenario}\n\n"
                "Contextual steps:\n{enriched_steps}\n\n"
                "Existing script reference (may be empty):\n{existing_script_excerpt}\n\n"
                "Scaffold snippets from the automation repository:\n{scaffold_snippet}\n\n"
                "Framework summary:\n{framework_summary}\n"
            ),
        )

        self.refine_prompt = PromptTemplate(
            input_variables=[
                "scenario",
                "previous_preview",
                "feedback",
                "enriched_steps",
                "scaffold_snippet",
                "framework_summary",
            ],
            template=(
                "You are refining previously proposed Playwright automation steps.\n"
                "Original scenario:\n{scenario}\n\n"
                "Previous preview steps:\n{previous_preview}\n\n"
                "User feedback:\n{feedback}\n\n"
                "Latest contextual recorder/UI steps:\n{enriched_steps}\n\n"
                "Relevant scaffold snippets:\n{scaffold_snippet}\n\n"
                "Framework summary:\n{framework_summary}\n\n"
                "Generate an improved numbered list of steps that addresses the feedback while preserving strong steps."
            ),
        )

        self.script_prompt = PromptTemplate(
            input_variables=[
                "scenario",
                "accepted_preview",
                "framework_summary",
                "locators_snippet",
                "pages_snippet",
                "tests_snippet",
                "slug",
            ],
            template=(
                "You are a senior Playwright framework engineer.\n"
                "Create implementation-ready artifacts for the scenario using the accepted preview steps.\n"
                "Follow the existing framework conventions showcased in the snippets.\n"
                "Return JSON ONLY with keys 'locators', 'pages', 'tests'.\n"
                "Each key must contain a list of objects {{\"path\": relative file path, \"content\": file contents}}.\n"
                "Use the slug '{slug}' to name new files consistently.\n"
                "Ensure TypeScript code compiles, uses proper imports, and references generated locators/pages.\n"
                "Do NOT wrap the JSON in code fences or add explanations.\n\n"
                "Scenario:\n{scenario}\n\n"
                "Accepted preview steps:\n{accepted_preview}\n\n"
                "Framework summary:\n{framework_summary}\n\n"
                "Locator examples:\n{locators_snippet}\n\n"
                "Page examples:\n{pages_snippet}\n\n"
                "Test examples:\n{tests_snippet}"
            ),
        )
    def _ensure_llm(self):
        """Instantiate the Azure LLM only when needed (preview/refine).
        Defers environment validation until first use so other endpoints don't 500.
        """
        if self.llm is None:
            if AzureChatOpenAI is None:
                raise RuntimeError("AzureChatOpenAI dependency not available; install langchain-openai")
            missing = [
                var for var in [
                    "OPENAI_API_VERSION",
                    "AZURE_OPENAI_DEPLOYMENT",
                    "AZURE_OPENAI_ENDPOINT",
                    "AZURE_OPENAI_KEY",
                ]
                if not os.getenv(var)
            ]
            if missing:
                raise RuntimeError(f"Missing Azure OpenAI env vars: {', '.join(missing)}")
            self.llm = AzureChatOpenAI(
                openai_api_version=os.getenv("OPENAI_API_VERSION"),
                azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT", "GPT-4o"),
                azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
                api_key=os.getenv("AZURE_OPENAI_KEY"),
                temperature=0.2,
            )
        return self.llm

    def gather_context(self, scenario: str) -> Dict[str, Any]:
        try:
            existing_script, recorder_flow, ui_crawl, test_case, structure, enriched_steps = (
                self.orchestrator.generate_script(scenario)
            )
        except Exception as exc:
            # Don't let context gathering break endpoints that can work with vector/FS only
            logger.warning("orchestrator.generate_script failed for scenario '%s': %s", scenario, exc)
            existing_script, recorder_flow, ui_crawl, test_case, structure, enriched_steps = (
                None, None, None, None, None, None
            )

        enriched_text = json.dumps(enriched_steps, indent=2) if enriched_steps else ""
        existing_excerpt = ""
        if existing_script and existing_script.get("content"):
            existing_excerpt = str(existing_script["content"])[:1200]

        vector_steps = self._collect_vector_flow_steps(scenario)
        vector_flow_name = vector_steps[0].get("flow_name") if vector_steps else ""
        vector_flow_slug = vector_steps[0].get("flow_slug") if vector_steps else ""
        if vector_steps:
            enriched_text = self._format_steps_for_prompt(vector_steps)

        scaffold_snippet = self._fetch_scaffold_snippet(scenario)

        return {
            "enriched_steps": enriched_text,
            "existing_script_excerpt": existing_excerpt,
            "scaffold_snippet": scaffold_snippet,
            "vector_steps": vector_steps,
            "artifacts": {
                "existing_script": existing_script,
                "recorder_flow": recorder_flow,
                "ui_crawl": ui_crawl,
                "test_case": test_case,
                "structure": structure,
            },
            "flow_available": bool(recorder_flow) or bool(vector_steps),
            "vector_flow": {
                "flow_name": vector_flow_name,
                "flow_slug": vector_flow_slug,
            } if vector_flow_name or vector_flow_slug else None,
        }

    def generate_preview(self, scenario: str, framework: FrameworkProfile, context: Dict[str, Any]) -> str:
        # Hard stop: if no grounded steps from recorder/vector, do not ask the LLM at all.
        enriched = context.get("enriched_steps", "").strip()
        vector_steps = context.get("vector_steps") or []
        if not enriched and not vector_steps:
            return (
                "INSUFFICIENT_CONTEXT: No recorder or vector-backed steps found. "
                "Please record the scenario or ingest relevant docs before generating a preview."
            )
        prompt = self.preview_prompt.format(
            scenario=scenario,
            enriched_steps=context.get("enriched_steps", ""),
            existing_script_excerpt=context.get("existing_script_excerpt", ""),
            scaffold_snippet=context.get("scaffold_snippet", ""),
            framework_summary=framework.summary(),
        )
        try:
            llm = self._ensure_llm()
        except Exception as exc:  # Environment/config issues
            logger.warning("LLM initialisation failed: %s", exc)
            # Fallback: emit grounded contextual steps directly so the UI can proceed
            if vector_steps:
                return self._format_steps_for_prompt(vector_steps)
            return enriched or f"LLM_NOT_AVAILABLE: {exc}"
        try:
            response = llm.invoke(prompt)
        except Exception as exc:
            logger.warning("LLM invoke failed for preview: %s", exc)
            if vector_steps:
                return self._format_steps_for_prompt(vector_steps)
            return enriched or f"LLM_NOT_AVAILABLE: {exc}"
        return _strip_code_fences(getattr(response, "content", str(response)))

    def refine_preview(
        self,
        scenario: str,
        framework: FrameworkProfile,
        previous_preview: str,
        feedback: str,
        context: Dict[str, Any],
    ) -> str:
        prompt = self.refine_prompt.format(
            scenario=scenario,
            previous_preview=previous_preview,
            feedback=feedback,
            enriched_steps=context.get("enriched_steps", ""),
            scaffold_snippet=context.get("scaffold_snippet", ""),
            framework_summary=framework.summary(),
        )
        try:
            llm = self._ensure_llm()
        except Exception as exc:
            logger.warning("LLM initialisation failed (refine): %s", exc)
            # Fallback: return previous preview if available, otherwise grounded steps
            if previous_preview.strip():
                return previous_preview
            steps = context.get("vector_steps") or []
            enriched = context.get("enriched_steps", "")
            return (self._format_steps_for_prompt(steps) if steps else enriched) or f"LLM_NOT_AVAILABLE: {exc}"
        try:
            response = llm.invoke(prompt)
        except Exception as exc:
            logger.warning("LLM invoke failed for refine: %s", exc)
            if previous_preview.strip():
                return previous_preview
            steps = context.get("vector_steps") or []
            enriched = context.get("enriched_steps", "")
            return (self._format_steps_for_prompt(steps) if steps else enriched) or f"LLM_NOT_AVAILABLE: {exc}"
        return _strip_code_fences(getattr(response, "content", str(response)))

    @staticmethod
    def _scenario_variants(scenario: str) -> Tuple[List[str], List[str]]:
        """Derive likely flow names and slugs from a free-form scenario request."""
        raw = (scenario or "").strip()
        if not raw:
            return [], []

        variants: List[str] = []
        seen_lower: set[str] = set()

        def _add_variant(text: str) -> None:
            cleaned = (text or "").strip(" -:,\n\t")
            if not cleaned:
                return
            lowered = cleaned.lower()
            if lowered not in seen_lower:
                seen_lower.add(lowered)
                variants.append(cleaned)

        _add_variant(raw)

        prefixes = [
            "generate automation script for",
            "generate test script for",
            "create automation script for",
            "create test script for",
            "automation script for",
            "automation scripts for",
            "automation for",
            "test scripts for",
            "test script for",
            "test cases for",
            "test case for",
            "script for",
            "scripts for",
        ]

        working = raw
        lowered = working.lower()
        for prefix in sorted(prefixes, key=len, reverse=True):
            if lowered.startswith(prefix):
                working = working[len(prefix) :].strip(" -:,\n\t")
                _add_variant(working)
                lowered = working.lower()
                break

        cleanup_patterns = [
            r"\bfrom\s+refined\s+recorder\s+flow\b",
            r"\bfrom\s+refined\s+flow\b",
            r"\bfrom\s+recorder\s+flow\b",
            r"\brefined\s+recorder\s+flow\b",
            r"\brefined\s+flow\b",
            r"\brecorder\s+flow\b",
            r"\bagentic\s+flow\b",
        ]
        cleaned = working
        for pattern in cleanup_patterns:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip(" -:,\n\t")

        trailing_suffixes = [
            " ui",
            " flow",
            " flows",
            " scenario",
            " test",
            " script",
        ]
        lower_cleaned = cleaned.lower()
        for suffix in trailing_suffixes:
            if lower_cleaned.endswith(suffix):
                cleaned = cleaned[: -len(suffix)].strip(" -:,\n\t")
                lower_cleaned = cleaned.lower()
                break

        _add_variant(cleaned)

        # Include a variant with the last segment after "for" if any text remains noisy.
        if " for " in raw.lower():
            tail = raw.lower().split(" for ", 1)[-1]
            _add_variant(tail)

        slug_variants: List[str] = []
        seen_slugs: set[str] = set()
        for text in variants:
            slug = _slugify(text)
            if slug and slug not in seen_slugs:
                slug_variants.append(slug)
                seen_slugs.add(slug)

        return variants, slug_variants

    @staticmethod
    def _select_best_slug(slug_hits: Counter, preferred_slugs: List[str]) -> Optional[str]:
        if not slug_hits:
            return None
        preferred_lower = [s.lower() for s in preferred_slugs]

        def _score(slug: str) -> Tuple[int, int]:
            try:
                idx = preferred_lower.index(slug.lower())
            except ValueError:
                idx = len(preferred_lower)
            return slug_hits[slug], -idx

        best = max(slug_hits, key=_score)
        return best if slug_hits[best] > 0 else None

    def _steps_from_vector_docs(
        self,
        docs: List[Dict[str, Any]],
        default_flow_slug: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        steps_map: Dict[int, Dict[str, str]] = {}
        resolved_name: Optional[str] = None
        resolved_slug = _slugify(default_flow_slug) if default_flow_slug else None
        for entry in docs or []:
            meta = (entry or {}).get("metadata") or {}
            record_kind = str(meta.get("record_kind") or "").lower()
            if record_kind and record_kind != "step":
                continue
            content = self._parse_content_snapshot(entry.get("content") or "")
            payload = content.get("payload") if isinstance(content, dict) else {}
            step_index = meta.get("step_index") or (payload or {}).get("step_index")
            try:
                step_no = int(step_index)
            except (TypeError, ValueError):
                continue
            action = (meta.get("action") or (payload or {}).get("action") or "").strip()
            navigation = (meta.get("navigation") or (payload or {}).get("navigation") or "").strip()
            data_val = (meta.get("data") or (payload or {}).get("data") or "").strip()
            expected = (meta.get("expected") or (payload or {}).get("expected") or "").strip()
            if not (action or navigation):
                continue
            flow_slug = meta.get("flow_slug") or (payload or {}).get("flow_slug") or resolved_slug or ""
            flow_name = meta.get("flow_name") or (payload or {}).get("flow") or resolved_name or ""
            resolved_name = flow_name or resolved_name
            resolved_slug = _slugify(flow_slug) if flow_slug else resolved_slug
            locator_info = (payload or {}).get("locators") or {}
            element_info = (payload or {}).get("element") or {}
            steps_map[step_no] = {
                "step": step_no,
                "action": action,
                "navigation": navigation,
                "data": data_val,
                "expected": expected,
                "flow_name": flow_name,
                "flow_slug": resolved_slug,
                "locators": locator_info,
                "element": element_info,
            }
        return [steps_map[idx] for idx in sorted(steps_map)]

    def _load_refined_flow_from_disk(
        self,
        slug_candidates: List[str],
        name_candidates: List[str],
    ) -> List[Dict[str, str]]:
        generated_dir = Path(__file__).resolve().parent / "generated_flows"
        if not generated_dir.exists():
            return []
        slug_lower = [s.lower() for s in slug_candidates if s]
        name_lower = [n.lower() for n in name_candidates if n]
        try:
            candidates = sorted(
                generated_dir.glob("*.refined.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        except Exception:
            return []
        for path in candidates:
            stem_lower = path.stem.lower()
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            flow_name = str(data.get("flow_name") or path.stem)
            flow_slug = _slugify(flow_name)
            if slug_lower and flow_slug.lower() not in slug_lower:
                if not any(slug in stem_lower for slug in slug_lower):
                    if name_lower and flow_name.lower() not in name_lower:
                        continue
            steps = data.get("steps") or []
            formatted: List[Dict[str, str]] = []
            for idx, step in enumerate(steps, start=1):
                step_no = step.get("step") or idx
                try:
                    step_no = int(step_no)
                except (TypeError, ValueError):
                    step_no = idx
                action = str(step.get("action") or "").strip()
                navigation = str(step.get("navigation") or "").strip()
                data_val = str(step.get("data") or "").strip()
                expected = str(step.get("expected") or "").strip()
                locators = step.get("locators") or {}
                if not isinstance(locators, dict):
                    locators = {}
                element = step.get("element") or {}
                if not isinstance(element, dict):
                    element = {}
                if not (action or navigation):
                    continue
                formatted.append(
                    {
                        "step": step_no,
                        "action": action,
                        "navigation": navigation,
                        "data": data_val,
                        "expected": expected,
                        "flow_name": flow_name,
                        "flow_slug": flow_slug,
                        "locators": locators,
                        "element": element,
                    }
                )
            if formatted:
                return sorted(formatted, key=lambda item: item["step"])
        return []

    def _collect_vector_flow_steps(self, scenario: str, top_k: int = 256) -> List[Dict[str, str]]:
        name_variants, slug_variants = self._scenario_variants(scenario)
        raw_specs: List[Dict[str, Any]] = []

        def _add_spec(query: str, where: Dict[str, Any]) -> None:
            if not query:
                return
            raw_specs.append({"query": query, "where": where})

        for slug in slug_variants:
            _add_spec(scenario, {"type": "recorder_refined", "flow_slug": slug})
            _add_spec(slug.replace("-", " "), {"type": "recorder_refined", "flow_slug": slug})

        for name in name_variants:
            slug = _slugify(name)
            _add_spec(name, {"type": "recorder_refined", "flow_slug": slug})
            _add_spec(name, {"type": "recorder_refined", "flow_name": name})

        fallback_queries = [scenario] + name_variants
        for query in fallback_queries:
            _add_spec(query, {"type": "recorder_refined"})

        specs: List[Dict[str, Any]] = []
        seen_spec: set[Tuple[str, str]] = set()
        for spec in raw_specs:
            key = (spec["query"], json.dumps(spec["where"], sort_keys=True))
            if key in seen_spec:
                continue
            seen_spec.add(key)
            specs.append(spec)

        slug_hits: Counter[str] = Counter()
        candidate_set = {slug.lower() for slug in slug_variants}
        selected_slug: Optional[str] = None
        flow_name_map: Dict[str, str] = {}

        for spec in specs:
            try:
                results = self.vector_db.query_where(spec["query"], spec["where"], top_k=top_k)
            except Exception:
                results = []
            for entry in results or []:
                meta = entry.get("metadata") or {}
                content = self._parse_content_snapshot(entry.get("content") or "")
                payload = content.get("payload") if isinstance(content, dict) else {}
                record_kind = (meta.get("record_kind") or (payload or {}).get("record_kind") or "").lower()
                if record_kind == "element":
                    continue
                flow_slug = (
                    meta.get("flow_slug")
                    or (payload or {}).get("flow_slug")
                    or meta.get("flowSlug")
                    or (payload or {}).get("flowSlug")
                    or ""
                )
                flow_slug = _slugify(flow_slug) if flow_slug else ""
                if not flow_slug:
                    continue
                slug_hits[flow_slug] += 1
                flow_name = meta.get("flow_name") or (payload or {}).get("flow") or ""
                flow_name_map.setdefault(flow_slug, flow_name)
                if flow_slug.lower() in candidate_set:
                    selected_slug = flow_slug
            if selected_slug:
                break

        if not selected_slug:
            selected_slug = self._select_best_slug(slug_hits, slug_variants)

        if selected_slug:
            try:
                docs = self.vector_db.list_where(
                    where={"type": "recorder_refined", "flow_slug": selected_slug},
                    limit=top_k,
                )
            except Exception:
                docs = []
            steps = self._steps_from_vector_docs(docs, default_flow_slug=selected_slug)
            if steps:
                flow_name = flow_name_map.get(selected_slug) or steps[0].get("flow_name") or ""
                # Ensure flow metadata is present on each step for downstream consumers.
                for step in steps:
                    step.setdefault("flow_slug", selected_slug)
                    if flow_name and not step.get("flow_name"):
                        step["flow_name"] = flow_name
                return steps

        return self._load_refined_flow_from_disk(slug_variants, name_variants)

    @staticmethod
    def _format_steps_for_prompt(steps: List[Dict[str, str]]) -> str:
        lines = []
        for item in steps:
            step_no = item.get("step")
            nav = item.get("navigation") or ""
            action = item.get("action") or ""
            data_val = item.get("data") or ""
            expected = item.get("expected") or ""
            parts = [part for part in [action, nav] if part]
            if data_val:
                parts.append(f"Data: {data_val}")
            if expected:
                parts.append(f"Expected: {expected}")
            if parts:
                lines.append(f"{step_no}. " + " | ".join(parts))
        return "\n".join(lines[:40])

    def _fetch_scaffold_snippet(self, scenario: str, limit: int = 3, max_chars: int = 1500) -> str:
        try:
            results = self.vector_db.query_where(
                scenario,
                where={"type": "script_scaffold"},
                top_k=limit,
            )
        except Exception:
            results = []

        snippets: List[str] = []
        for entry in results or []:
            metadata = entry.get("metadata") or {}
            content_obj = self._parse_content_snapshot(entry.get("content", ""))
            path = metadata.get("file_path") or ""
            code = ""
            if isinstance(content_obj, dict):
                path = content_obj.get("filePath") or content_obj.get("path") or path
                code = content_obj.get("content") or content_obj.get("body") or ""
            elif isinstance(content_obj, list):
                for item in content_obj:
                    if isinstance(item, dict) and not code:
                        path = item.get("filePath") or path
                        code = item.get("content") or item.get("body") or ""
            if not code:
                code = str(entry.get("content") or "")
            snippet = ""
            if path:
                snippet += f"// {path}\n"
            snippet += code.strip()
            if snippet:
                snippets.append(snippet[:max_chars])
            if sum(len(s) for s in snippets) >= max_chars:
                break
        return "\n\n".join(snippets)[:max_chars]

    @staticmethod
    def _parse_content_snapshot(content: str) -> Optional[Dict[str, Any]]:
        if not content:
            return None
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass
        try:
            return ast.literal_eval(content)
        except (SyntaxError, ValueError):
            return None

    @staticmethod
    def _candidate_paths_from_metadata(metadata: Dict[str, Any], content_obj: Optional[Dict[str, Any]]) -> List[str]:
        candidates = []
        keys = [
            "file_path",
            "path",
            "filePath",
            "relative_path",
            "relativePath",
            "module_path",
            "modulePath",
        ]
        for key in keys:
            value = metadata.get(key)
            if value:
                candidates.append(str(value))
        if content_obj:
            for key in keys + ["name", "fileName", "filename"]:
                value = content_obj.get(key)
                if value:
                    candidates.append(str(value))
        return candidates

    @staticmethod
    def _normalize_relative_path(candidate: str) -> Optional[str]:
        if not candidate:
            return None
        normalized = candidate.replace("\\", "/")
        markers = ["/locators/", "/pages/", "/tests/", "/features/", "/steps/"]
        lowered = normalized.lower()
        for marker in markers:
            idx = lowered.rfind(marker)
            if idx != -1:
                rel = normalized[idx + 1 :]
                return rel
        if re.match(r"^[a-zA-Z]:", normalized):
            return None
        if normalized.startswith("/tmp"):
            return None
        return normalized

    def _locate_framework_file(
        self, framework: FrameworkProfile, metadata: Dict[str, Any], content_str: str
    ) -> Optional[Path]:
        content_obj = self._parse_content_snapshot(content_str)
        candidates = self._candidate_paths_from_metadata(metadata, content_obj)
        for candidate in candidates:
            normalized = candidate.replace("\\", "/")
            framework_root_norm = str(framework.root.resolve()).replace("\\", "/").lower()
            lowered = normalized.lower()
            if lowered.startswith(framework_root_norm):
                rel = normalized[len(framework_root_norm):].lstrip("/")
                target = (framework.root / Path(rel)).resolve()
                if target.exists():
                    return target
            rel = self._normalize_relative_path(normalized)
            if rel:
                target = (framework.root / Path(rel)).resolve()
                if target.exists():
                    return target
            name = Path(normalized).name
            if name:
                matches = list(framework.root.rglob(name))
                if matches:
                    return matches[0]
        if content_obj and "name" in content_obj:
            matches = list(framework.root.rglob(content_obj["name"]))
            if matches:
                return matches[0]
        return None

    def find_existing_framework_assets(
        self, scenario: str, framework: FrameworkProfile, top_k: int = 8
    ) -> List[Dict[str, Any]]:
        try:
            results = self.vector_db.query(scenario, top_k=top_k)
        except Exception as exc:
            logger.warning("vector_db.query failed for scenario '%s': %s", scenario, exc)
            results = []
        assets: List[Dict[str, Any]] = []
        min_score = 6  # threshold to avoid unrelated matches
        scenario_tokens = self._tokenize(scenario)
        scenario_terms = {tok for tok in scenario_tokens if tok}

        def _path_matches(path_obj: Path) -> bool:
            lowered = str(path_obj).lower()
            return any(term in lowered for term in scenario_terms)

        for entry in results:
            metadata = entry.get("metadata", {}) or {}
            meta_type = str(metadata.get("type", "")) + str(metadata.get("artifact_type", ""))
            if not any(token in meta_type.lower() for token in ["script", "scaffold", "locator", "page", "test"]):
                continue
            content_str = entry.get("content", "")
            path = self._locate_framework_file(framework, metadata, content_str)
            if path and path.exists():
                if scenario_terms and not _path_matches(path):
                    continue
                try:
                    file_content = path.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    file_content = ""
                score = self._compute_relevance_score(path, file_content, scenario_tokens)
                if score >= min_score:
                    assets.append({
                        "path": path,
                        "metadata": {**metadata, "relevance_score": score, "source": "vector+repo"},
                        "id": entry.get("id"),
                    })
        # Fallback: direct repo scan if vector search found nothing
        if not assets:
            assets = self._filesystem_search_assets(framework, scenario, max_results=top_k)
        return assets

    def _filesystem_search_assets(self, framework: FrameworkProfile, scenario: str, max_results: int = 8) -> List[Dict[str, Any]]:
        """Search the framework repo for likely matching files when vector DB has no hits.
        Heuristics: match by filename and file content tokens under tests/pages/locators.
        """
        root = framework.root
        search_dirs: List[Path] = []
        for d in [framework.tests_dir, framework.pages_dir, framework.locators_dir]:
            if d and d.exists():
                search_dirs.append(d)
        search_dirs.extend(framework.additional_dirs.values())
        if not search_dirs:
            search_dirs = [root]

        tokens = self._tokenize(scenario)
        slug = _slugify(scenario)
        slug_parts = self._tokenize(slug)

        candidates: List[Tuple[int, Path]] = []
        seen: set[Path] = set()
        min_score = 6
        penalty_terms = {"supplier", "receipt", "invoice", "arinvoice", "apinvoice", "ap", "po", "procurement"}

        for base in search_dirs:
            for path in base.rglob("*.ts"):
                if path in seen:
                    continue
                seen.add(path)
                score = 0
                name = path.name.lower()
                # Filename match
                for t in slug_parts + tokens:
                    if t and t in name:
                        score += 3
                # Content match (lightweight)
                try:
                    content = path.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    content = ""
                low = content.lower()
                # Exact phrase boost
                phrase = " ".join(tokens)
                if phrase and phrase in low:
                    score += 4
                # Token overlap
                for t in tokens[:6]:  # cap tokens for perf
                    if t and t in low:
                        score += 1
                # Domain penalty if unrelated terms appear but not in scenario tokens
                for p in penalty_terms:
                    if p in low and p not in tokens:
                        score -= 2
                # Prefer tests over pages/locators in tie
                try:
                    rel = path.relative_to(root)
                    rel_low = str(rel).lower()
                    if any(seg in rel_low for seg in ["/tests/", "/specs/", "/e2e/"]):
                        score += 1
                except Exception:
                    pass
                if score > 0:
                    candidates.append((score, path))

        candidates.sort(key=lambda x: x[0], reverse=True)
        # Apply threshold to avoid unrelated matches
        filtered = [
            (s, p)
            for s, p in candidates
            if s >= min_score and (not tokens or any(t in str(p).lower() for t in tokens))
        ]
        results: List[Dict[str, Any]] = []
        for score, p in filtered[:max_results]:
            results.append({
                "path": p,
                "metadata": {"source": "filesystem", "relevance_score": score},
                "id": None,
            })
        return results

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        return [tok for tok in re.split(r"[^a-zA-Z0-9]+", (text or "").lower()) if len(tok) >= 3]

    def _compute_relevance_score(self, path: Path, content: str, scenario_tokens: List[str]) -> int:
        """Compute a simple relevance score combining filename and content overlaps.
        Adds a boost for exact phrase and test locations; penalizes common unrelated domains.
        """
        name = path.name.lower()
        score = 0
        for t in scenario_tokens:
            if t in name:
                score += 3
        low = (content or "").lower()
        phrase = " ".join(scenario_tokens)
        if phrase and phrase in low:
            score += 4
        for t in scenario_tokens[:6]:
            if t in low:
                score += 1
        try:
            rel_low = str(path).lower()
            if any(seg in rel_low for seg in ["/tests/", "/specs/", "/e2e/"]):
                score += 1
        except Exception:
            pass
        penalty_terms = {"supplier", "receipt", "invoice", "arinvoice", "apinvoice", "ap", "po", "procurement"}
        for p in penalty_terms:
            if p in low and p not in scenario_tokens:
                score -= 2
        return score

    def generate_script_payload(
        self,
        scenario: str,
        framework: FrameworkProfile,
        accepted_preview: str,
    ) -> Dict[str, List[Dict[str, str]]]:
        context = self.gather_context(scenario)
        vector_steps = context.get("vector_steps") or []
        if not vector_steps:
            raise ValueError(
                "No refined recorder steps available for this scenario. "
                "Please ingest the refined flow or record the scenario again."
            )
        keep_signatures = _extract_preview_signatures(accepted_preview)
        # Also extract navigation/action phrases for fuzzy alignment
        preview_phrases = _extract_preview_phrases(accepted_preview)

        # If signatures are too few, disable strict filtering
        final_signatures = None if (keep_signatures is not None and len(keep_signatures) < 2) else keep_signatures

        # If signatures exist but don't align well with vector steps, try phrase-based filtering
        if final_signatures:
            matched = [step for step in vector_steps if _step_signature(step) in final_signatures]
            # Heuristic: if signature matching keeps <50% of preview lines or 0, try phrase filter
            if not matched or (preview_phrases and len(matched) < max(2, len(preview_phrases) // 2)):
                def _matches_phrase(step: Dict[str, Any]) -> bool:
                    nav = _normalize_for_match(step.get("navigation") or step.get("action") or "")
                    if not nav:
                        return False
                    for phrase in preview_phrases:
                        if not phrase:
                            continue
                        # Accept substring either way to cope with small wording drift
                        if phrase in nav or nav in phrase:
                            return True
                    return False
                fuzzy = [s for s in vector_steps if _matches_phrase(s)]
                if fuzzy:
                    return self._build_deterministic_payload(scenario, framework, fuzzy, keep_signatures=None)

        return self._build_deterministic_payload(scenario, framework, vector_steps, keep_signatures=final_signatures)

    def _build_deterministic_payload(
        self,
        scenario: str,
        framework: FrameworkProfile,
        vector_steps: List[Dict[str, Any]],
        keep_signatures: Optional[Set[str]] = None,
    ) -> Dict[str, List[Dict[str, str]]]:
        slug = _slugify(scenario)
        root = framework.root

        def resolve_relative(target: Path) -> str:
            return str(target.relative_to(root)).replace('\\', '/')

        if framework.locators_dir:
            locators_path = framework.locators_dir / f"{slug}.ts"
        else:
            locators_path = root / 'locators' / f"{slug}.ts"
        if framework.pages_dir:
            page_filename = f"{_to_camel_case(slug).capitalize() or 'Generated'}Page.ts"
            page_path = framework.pages_dir / page_filename
        else:
            page_path = root / 'pages' / f"{_to_camel_case(slug).capitalize() or 'Generated'}Page.ts"
        if framework.tests_dir:
            test_path = framework.tests_dir / f"{slug}.spec.ts"
        else:
            test_path = root / 'tests' / f"{slug}.spec.ts"

        search_dirs: List[Path] = []
        if framework.pages_dir and framework.pages_dir.exists():
            search_dirs.append(framework.pages_dir)
        else:
            fallback_pages_dir = root / 'pages'
            if fallback_pages_dir.exists():
                search_dirs.append(fallback_pages_dir)

        login_page_file: Optional[Path] = None
        home_page_file: Optional[Path] = None

        for directory in search_dirs:
            matches = list(directory.glob('**/login.page.ts'))
            if matches:
                login_page_file = matches[0]
                break

        for directory in search_dirs:
            matches = list(directory.glob('**/home.page.ts'))
            if matches:
                home_page_file = matches[0]
                break

        login_key_candidates = {
            "username",
            "userid",
            "user",
            "signin",
            "sign_in",
            "password",
            "enterpasscode",
            "passcode",
            "verify",
        }

        selector_to_key: Dict[str, str] = {}
        used_keys: set[str] = set()
        entries: List[Tuple[str, str]] = []
        entry_keys: set[str] = set()
        step_refs: List[Dict[str, Any]] = []
        data_bindings: List[Dict[str, Any]] = []
        method_names: set[str] = set()

        if keep_signatures is not None and len(keep_signatures) < 2:
            keep_signatures = None

        effective_steps: List[Dict[str, Any]]
        if keep_signatures:
            filtered_steps = [
                step for step in vector_steps if _step_signature(step) in keep_signatures
            ]
            effective_steps = filtered_steps or vector_steps
        else:
            effective_steps = vector_steps

        for index, step in enumerate(effective_steps):
            locators = step.get('locators') or {}
            signature = _step_signature(step)
            if keep_signatures is not None and signature not in keep_signatures:
                continue
            selector = _normalize_selector(
                locators.get('css')
                or locators.get('playwright')
                or locators.get('stable')
                or locators.get('xpath')
                or locators.get('raw_xpath')
                or locators.get('selector')
                or ''
            )
            if not selector:
                element = step.get('element') or {}
                selector = _normalize_selector(
                    element.get('css')
                    or element.get('playwright')
                    or element.get('stable')
                    or element.get('xpath')
                    or element.get('raw_xpath')
                )
            if not selector:
                raise ValueError(
                    f"No selector resolved for step {index + 1} "
                    f"(action={step.get('action')!r}, navigation={step.get('navigation')!r}). "
                    'Ensure the refined recorder flow includes CSS or stable selectors.'
                )

            if selector in selector_to_key:
                key = selector_to_key[selector]
            else:
                base_name = (
                    locators.get('name')
                    or locators.get('title')
                    or locators.get('labels')
                    or step.get('navigation')
                    or step.get('action')
                    or f'step{index + 1}'
                )
                base_key = _to_camel_case(base_name) or f'step{index + 1}'
                key = base_key
                suffix = 2
                while key in used_keys:
                    key = f"{base_key}{suffix}"
                    suffix += 1
                selector_to_key[selector] = key
                used_keys.add(key)

            navigation = step.get('navigation') or ''
            nav_lower = navigation.lower()
            handled_by: Optional[str] = None
            key_lower = key.lower()

            if login_page_file:
                login_keywords = [
                    'user name',
                    'username',
                    'password',
                    'sign in',
                    'signin',
                    'passcode',
                    'verify',
                    'login page',
                ]
                if any(term in nav_lower for term in login_keywords) or any(candidate in key_lower for candidate in login_key_candidates):
                    handled_by = 'login'

            if not handled_by and key not in entry_keys:
                entries.append((key, selector))
                entry_keys.add(key)

            step_ref: Dict[str, Any] = {
                'key': key,
                'action': (step.get('action') or '').lower(),
                'data': _extract_data_value(step),
                'raw': step,
            }
            if handled_by:
                step_ref['handled_by'] = handled_by
            step_refs.append(step_ref)

            data_key = _extract_data_key(step)
            if data_key and not handled_by:
                action_lower = (step.get('action') or '').lower()
                action_category = 'fill'
                if 'select' in action_lower or 'dropdown' in nav_lower or 'choose' in nav_lower:
                    action_category = 'select'
                method_suffix = _to_camel_case(data_key) or _to_camel_case(navigation) or key
                if method_suffix:
                    method_suffix = method_suffix[:1].upper() + method_suffix[1:]
                else:
                    method_suffix = key.title()
                prefix = 'set' if action_category != 'select' else 'select'
                candidate_name = prefix + (method_suffix[:1].upper() + method_suffix[1:])
                if candidate_name in method_names:
                    counter = 2
                    base_candidate = candidate_name
                    while candidate_name in method_names:
                        candidate_name = f"{base_candidate}{counter}"
                        counter += 1
                method_names.add(candidate_name)
                normalised_key = re.sub(r'[^a-z0-9]+', '', data_key.lower())
                data_bindings.append(
                    {
                        'locator_key': key,
                        'data_key': data_key,
                        'normalised': normalised_key,
                        'method_name': candidate_name,
                        'fallback': _extract_data_value(step),
                        'action_category': action_category,
                    }
                )
                step_ref['data_key'] = data_key
                step_ref['method_name'] = candidate_name
                step_ref['action_category'] = action_category

        locators_lines = ['const locators = {'] + [
            f"  {key}: {json.dumps(selector)}," for key, selector in entries
        ] + ['};', '', 'export default locators;']
        locators_content = "\n".join(locators_lines) + os.linesep

        page_class = _to_camel_case(Path(page_path).stem).capitalize() or 'GeneratedPage'
        page_var = page_class[:1].lower() + page_class[1:] if page_class else 'pageObject'
        page_lines: List[str] = [
            "import { Page, Locator } from '@playwright/test';",
            f'import locators from "{_relative_import(page_path, locators_path)}";',
        ]

        helper_candidates = [
            root / 'util' / 'methods.utility.ts',
            root / 'util' / 'methods.utility',
            root / 'utils' / 'methods.utility.ts',
            root / 'utils' / 'methods.utility',
        ]
        helper_path = next((candidate for candidate in helper_candidates if candidate.exists()), None)
        helper_available = helper_path is not None
        if helper_available:
            page_lines.insert(
                1,
                f'import HelperClass from "{_relative_import(page_path, helper_path)}";',
            )
        for binding in data_bindings:
            binding['use_helper'] = helper_available and binding['action_category'] == 'select'

        page_lines.append('')
        page_lines.append(f'class {page_class} {{')
        page_lines.append('  page: Page;')
        if helper_available:
            page_lines.append('  helper: HelperClass;')
        for key, _ in entries:
            page_lines.append(f'  {key}: Locator;')
        page_lines.append('')
        page_lines.append('  constructor(page: Page) {')
        page_lines.append('    this.page = page;')
        if helper_available:
            page_lines.append('    this.helper = new HelperClass(page);')
        for key, _ in entries:
            page_lines.append(f'    this.{key} = page.locator(locators.{key});')
        page_lines.append('  }')

        if data_bindings:
            page_lines.append('')
            page_lines.append("  private coerceValue(value: unknown): string {")
            page_lines.append("    if (value === undefined || value === null) {")
            page_lines.append("      return '';")
            page_lines.append('    }')
            page_lines.append("    if (typeof value === 'number') {")
            page_lines.append("      return `${value}`;")
            page_lines.append('    }')
            page_lines.append("    if (typeof value === 'string') {")
            page_lines.append('      return value;')
            page_lines.append('    }')
            page_lines.append("    return `${value ?? ''}`;")
            page_lines.append('  }')
            page_lines.append('')
            page_lines.append("  private normaliseDataKey(value: string): string {")
            page_lines.append("    return (value || '').replace(/[^a-z0-9]+/gi, '').toLowerCase();")
            page_lines.append('  }')
            page_lines.append('')
            page_lines.append("  private resolveDataValue(formData: Record<string, any> | null | undefined, key: string, fallback: string = ''): string {")
            page_lines.append('    const target = this.normaliseDataKey(key);')
            page_lines.append('    if (formData) {')
            page_lines.append('      for (const entryKey of Object.keys(formData)) {')
            page_lines.append('        if (this.normaliseDataKey(entryKey) === target) {')
            page_lines.append('          const candidate = this.coerceValue(formData[entryKey]);')
            page_lines.append("          if (candidate.trim() !== '') {")
            page_lines.append('            return candidate;')
            page_lines.append('          }')
            page_lines.append('        }')
            page_lines.append('      }')
            page_lines.append('    }')
            page_lines.append('    return this.coerceValue(fallback);')
            page_lines.append('  }')

        fallback_map: Dict[str, str] = {}
        for binding in data_bindings:
            fallback_map[binding['data_key']] = ""

        for binding in data_bindings:
            method_name = binding['method_name']
            locator_key = binding['locator_key']
            action_category = binding['action_category']
            use_helper = binding['use_helper']
            page_lines.append('')
            page_lines.append(f'  async {method_name}(value: unknown): Promise<void> {{')
            page_lines.append('    const finalValue = this.coerceValue(value);')
            if action_category == 'select' and use_helper:
                page_lines.append(f'    await this.helper.compoundElementSelection(this.{locator_key}, finalValue);')
            elif action_category == 'select':
                page_lines.append(f'    await this.{locator_key}.selectOption(finalValue);')
            else:
                page_lines.append(f'    await this.{locator_key}.fill(finalValue);')
            page_lines.append('  }')

        if data_bindings:
            page_lines.append('')
            page_lines.append('  async applyData(formData: Record<string, any> | null | undefined, keys?: string[]): Promise<void> {')
            page_lines.append('    const fallbackValues: Record<string, string> = {')
            for data_key, fallback in fallback_map.items():
                page_lines.append(f"      {json.dumps(data_key)}: {json.dumps(fallback or '')},")
            page_lines.append('    };')
            page_lines.append('    const targetKeys = Array.isArray(keys) && keys.length ? keys.map((key) => this.normaliseDataKey(key)) : null;')
            page_lines.append('    const shouldHandle = (key: string) => {')
            page_lines.append('      if (!targetKeys) {')
            page_lines.append('        return true;')
            page_lines.append('      }')
            page_lines.append('      return targetKeys.includes(this.normaliseDataKey(key));')
            page_lines.append('    };')
            for binding in data_bindings:
                data_key = binding['data_key']
                method_name = binding['method_name']
                page_lines.append(f"    if (shouldHandle({json.dumps(data_key)})) {{")
                page_lines.append(f"      await this.{method_name}(this.resolveDataValue(formData, {json.dumps(data_key)}, fallbackValues[{json.dumps(data_key)}] ?? ''));")
                page_lines.append('    }')
            page_lines.append('  }')

        page_lines.append('}')
        page_lines.append('')
        page_lines.append(f'export default {page_class};')
        page_content = "\n".join(page_lines) + os.linesep

        scenario_literal = json.dumps(scenario)
        spec_lines = [
            'import { test } from "./testSetup.ts";',
            f'import PageObject from "{_relative_import(test_path, page_path)}";',
        ]
        if login_page_file:
            spec_lines.append(f'import LoginPage from "{_relative_import(test_path, login_page_file)}";')
        if home_page_file:
            spec_lines.append(f'import HomePage from "{_relative_import(test_path, home_page_file)}";')

        spec_lines.extend([
            'import { getTestToRun, shouldRun, readExcelData } from "../util/csvFileManipulation.ts";',
            'import { attachScreenshot, namedStep } from "../util/screenshot.ts";',
            "import * as dotenv from 'dotenv';",
            '',
            "const path = require('path');",
            "const fs = require('fs');",
            '',
            'dotenv.config();',
            'let executionList: any[];',
            '',
            'test.beforeAll(() => {',
            "  executionList = getTestToRun(path.join(__dirname, '../testmanager.xlsx'));",
            '});',
            '',
            f'test.describe({scenario_literal}, () => {{',
            f'  let {page_var}: PageObject;',
        ])

        if login_page_file:
            spec_lines.append('  let loginPage: LoginPage;')
        if home_page_file:
            spec_lines.append('  let homePage: HomePage;')
        spec_lines.append('')
        spec_lines.append('  const run = (name: string, fn: ({ page }, testinfo: any) => Promise<void>) =>')
        spec_lines.append('    (shouldRun(name) ? test : test.skip)(name, fn);')
        spec_lines.append('')
        spec_lines.append(f'  run({scenario_literal}, async ({{ page }}, testinfo) => {{')
        spec_lines.append(f'    {page_var} = new PageObject(page);')
        if login_page_file:
            spec_lines.append('    loginPage = new LoginPage(page);')
        if home_page_file:
            spec_lines.append('    homePage = new HomePage(page);')
        spec_lines.extend([
            '    const testCaseId = testinfo.title;',
            "    const testRow: Record<string, any> = executionList?.find((row: any) => row['TestCaseID'] === testCaseId) ?? {};",
            '    const defaultDataStem = (() => {',
            "      const core = testCaseId.replace(/[^a-z0-9]+/gi, ' ').trim();",
            "      if (!core) {",
            "        return 'TestData';",
            '      }',
            r"      return core.split(/\s+/).map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join('');",
            '    })();',
            "    const defaultDatasheetName = `${defaultDataStem}Data.xlsx`;",
            "    const defaultIdColumn = `${defaultDataStem}ID`;",
            "    const defaultReferenceId = `${defaultDataStem}001`;",
            "    const dataSheetName = String(testRow?.['DatasheetName'] ?? '').trim() || defaultDatasheetName;",
            "    const dataReferenceId = String(testRow?.['ReferenceID'] ?? '').trim() || defaultReferenceId;",
            "    const dataIdColumn = String(testRow?.['IDName'] ?? '').trim() || defaultIdColumn;",
            "    const dataSheetTab = String(testRow?.['SheetName'] ?? testRow?.['Sheet'] ?? '').trim();",
            "    const dataDir = path.join(__dirname, '../data');",
            '    fs.mkdirSync(dataDir, { recursive: true });',
            '    let dataRow: Record<string, any> = {};',
            '    const ensureDataFile = (): string | null => {',
            '      if (!dataSheetName) {',
            "        console.warn(`[DATA] DatasheetName missing for ${testCaseId}; using generated defaults.`);",
            '        return null;',
            '      }',
            '      const expectedPath = path.join(dataDir, dataSheetName);',
            '      if (!fs.existsSync(expectedPath)) {',
            '        const caseInsensitiveMatch = (() => {',
            '          try {',
            '            const entries = fs.readdirSync(dataDir, { withFileTypes: false });',
            '            const target = dataSheetName.toLowerCase();',
            '            const found = entries.find((entry) => entry.toLowerCase() === target);',
            '            return found ? path.join(dataDir, found) : null;',
            '          } catch (err) {',
            "            console.warn(`[DATA] Unable to scan data directory for ${dataSheetName}:`, err);",
            '            return null;',
            '          }',
            '        })();',
            '        if (caseInsensitiveMatch) {',
            '          return caseInsensitiveMatch;',
            '        }',
            "        const message = `Test data file '${dataSheetName}' not found in data/. Upload the file before running '${testCaseId}'.`;",
            "        console.warn(`[DATA] ${message}`);",
            '        throw new Error(message);',
            '      }',
            '      return expectedPath;',
            '    };',
            "    const normaliseKey = (value: string) => value.replace(/[^a-z0-9]/gi, '').toLowerCase();",
            '    const findMatchingDataKey = (sourceKey: string) => {',
            '      if (!sourceKey || !dataRow) {',
            '        return undefined;',
            '      }',
            '      const normalisedSource = normaliseKey(sourceKey);',
            '      return Object.keys(dataRow || {}).find((candidate) => normaliseKey(String(candidate)) === normalisedSource);',
            '    };',
            '    const getDataValue = (sourceKey: string, fallback: string) => {',
            '      if (!sourceKey) {',
            '        return fallback;',
            '      }',
            "      const directKey = findMatchingDataKey(sourceKey) || findMatchingDataKey(sourceKey.replace(/([A-Z])/g, '_$1'));",
            '      if (directKey) {',
            '        const candidate = dataRow?.[directKey];',
            "        if (candidate !== undefined && candidate !== null && `${candidate}`.trim() !== '') {",
            '          return `${candidate}`;',
            '        }',
            '      }',
            '      return fallback;',
            '    };',
            '    const dataPath = ensureDataFile();',
            '    if (dataPath && dataReferenceId && dataIdColumn) {',
            "      dataRow = readExcelData(dataPath, dataSheetTab || '', dataReferenceId, dataIdColumn) ?? {};",
            '      if (!dataRow || Object.keys(dataRow).length === 0) {',
            "        console.warn(`[DATA] Row not found in ${dataSheetName} for ${dataIdColumn}='${dataReferenceId}'.`);",
            '      }',
            '    } else if (dataSheetName) {',
            "      console.warn(`[DATA] DatasheetName provided but ReferenceID/IDName missing for ${testCaseId}. Generated defaults will be used.`);",
            '    }',
            '',
        ])

        login_step_emitted = False
        has_data_bindings = bool(data_bindings)

        for idx, ref in enumerate(step_refs, start=1):
            raw = ref.get('raw') or {}
            note = raw.get('navigation') or raw.get('action') or raw.get('expected') or f'Step {idx}'
            step_title = json.dumps(f'Step {idx} - {note}')
            comment = raw.get('navigation') or raw.get('action') or ''
            key = ref.get('key')
            action = ref.get('action') or ''
            data_value = ref.get('data') or ''
            locator_expr = f"{page_var}.{key}" if key else ''
            handled_by = ref.get('handled_by')
            home_method = ref.get('home_method')

            if handled_by == 'login' and login_page_file:
                if not login_step_emitted:
                    spec_lines.append(f'    await namedStep({step_title}, page, testinfo, async () => {{')
                    if comment:
                        spec_lines.append(f'      // {comment}')
                    spec_lines.append('      await loginPage.goto();')
                    spec_lines.append("      await loginPage.login(process.env.USERID ?? '', process.env.PASSWORD ?? '');")
                    spec_lines.append('      const screenshot = await page.screenshot();')
                    spec_lines.append(f'      attachScreenshot({step_title}, testinfo, screenshot);')
                    if raw.get('expected'):
                        spec_lines.append(f"      // Expected: {raw['expected']}")
                    spec_lines.append('    });')
                    spec_lines.append('')
                    login_step_emitted = True
                continue

            spec_lines.append(f'    await namedStep({step_title}, page, testinfo, async () => {{')
            if comment:
                spec_lines.append(f'      // {comment}')
            fallback_literal = json.dumps(data_value or '')
            data_expr = fallback_literal
            if key:
                data_expr = f"getDataValue({json.dumps(key)}, {fallback_literal})"

            if has_data_bindings and ref.get('data_key'):
                keys_literal = json.dumps([ref['data_key']])
                spec_lines.append(f'      await {page_var}.applyData(dataRow, {keys_literal});')
            elif key and any(token in action for token in ['fill', 'type', 'enter']):
                spec_lines.append(f'      await {locator_expr}.fill({data_expr});')
            elif key and 'select' in action:
                spec_lines.append(f'      await {locator_expr}.selectOption({data_expr});')
            elif key and 'press' in action:
                press_value = json.dumps(data_value or 'Enter')
                spec_lines.append(f'      await {locator_expr}.press({press_value});')
            elif 'goto' in action or 'navigate' in action:
                spec_lines.append(f'      await page.goto({data_expr});')
            elif key:
                spec_lines.append(f'      await {locator_expr}.click();')
            else:
                spec_lines.append('      // TODO: No selector provided by refined flow.')
            if raw.get('expected'):
                spec_lines.append(f"      // Expected: {raw['expected']}")
            spec_lines.append('      const screenshot = await page.screenshot();')
            spec_lines.append(f'      attachScreenshot({step_title}, testinfo, screenshot);')
            spec_lines.append('    });')
            spec_lines.append('')
        spec_lines.append('  });')
        spec_lines.append('});')
        spec_content = "\n".join(spec_lines).rstrip() + os.linesep

        return {
            'locators': [
                {'path': resolve_relative(locators_path), 'content': locators_content}
            ],
            'pages': [
                {'path': resolve_relative(page_path), 'content': page_content}
            ],
            'tests': [
                {'path': resolve_relative(test_path), 'content': spec_content}
            ],
        }

    @staticmethod
    def persist_payload(framework: FrameworkProfile, payload: Dict[str, List[Dict[str, str]]]) -> List[Path]:
        written_paths: List[Path] = []
        root_resolved = framework.root.resolve()
        for files in payload.values():
            for file_obj in files:
                rel_path = Path(file_obj["path"])
                target = (framework.root / rel_path).resolve()
                if os.path.commonpath([root_resolved, target]) != str(root_resolved):
                    raise ValueError(f"Attempted to write outside repo root: {rel_path}")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(file_obj["content"], encoding="utf-8")
                written_paths.append(target)
        return written_paths

    @staticmethod
    def push_changes(framework: FrameworkProfile, branch: str, commit_msg: str) -> bool:
        return push_to_git(str(framework.root), branch=branch, commit_msg=commit_msg)


def initialise_agentic_state() -> Dict[str, Any]:
    return {
        "active": False,
        "scenario": "",
        "status": "idle",
        "preview": "",
        "feedback": [],
        "context": {},
        "payload": {},
        "written_files": [],
        "pending_test_ids": [],
        "pending_datasheet_defaults": None,
        "datasheet_values": None,
        "awaiting_datasheet": False,
    }


def interpret_confirmation(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in ["confirm", "looks good", "proceed", "go ahead", "approved"])


def interpret_push(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in ["push", "commit", "publish", "merge", "deploy"])


def interpret_feedback(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in ["feedback", "change", "modify", "update", "adjust", "revise"])
