"""Agentic workflow for generating Playwright test scripts aligned with framework standards."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import ast

from langchain.prompts import PromptTemplate
from langchain_openai import AzureChatOpenAI

from orchestrator import TestScriptOrchestrator
from git_utils import push_to_git
from vector_db import VectorDBClient


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
        for name in ["fixtures", "data", "utils", "support"]:
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


class AgenticScriptAgent:
    def __init__(self):
        self.llm = AzureChatOpenAI(
            openai_api_version=os.getenv("OPENAI_API_VERSION"),
            azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT", "GPT-4o"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_key=os.getenv("AZURE_OPENAI_KEY"),
            temperature=0.2,
        )
        self.orchestrator = TestScriptOrchestrator()
        self.vector_db = VectorDBClient()

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
                "Design a concise, numbered list of Playwright automation steps for the scenario described below.\n"
                "Incorporate relevant context when available, but ensure each step is action-oriented and precise.\n"
                "Respond with Markdown numbered steps only.\n\n"
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

    def gather_context(self, scenario: str) -> Dict[str, Any]:
        existing_script, recorder_flow, ui_crawl, test_case, structure, enriched_steps = (
            self.orchestrator.generate_script(scenario)
        )

        enriched_text = json.dumps(enriched_steps, indent=2) if enriched_steps else ""
        existing_excerpt = ""
        if existing_script and existing_script.get("content"):
            existing_excerpt = str(existing_script["content"])[:1200]

        vector_steps = self._collect_vector_flow_steps(scenario)
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
        }

    def generate_preview(self, scenario: str, framework: FrameworkProfile, context: Dict[str, Any]) -> str:
        prompt = self.preview_prompt.format(
            scenario=scenario,
            enriched_steps=context.get("enriched_steps", ""),
            existing_script_excerpt=context.get("existing_script_excerpt", ""),
            scaffold_snippet=context.get("scaffold_snippet", ""),
            framework_summary=framework.summary(),
        )
        response = self.llm.invoke(prompt)
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
        response = self.llm.invoke(prompt)
        return _strip_code_fences(getattr(response, "content", str(response)))

    def _collect_vector_flow_steps(self, scenario: str, top_k: int = 256) -> List[Dict[str, str]]:
        slug = _slugify(scenario)
        specs = [
            {"query": scenario, "where": {"type": "recorder_refined", "flow_slug": slug}},
            {"query": slug, "where": {"type": "recorder_refined", "flow_slug": slug}},
            {"query": scenario, "where": {"type": "recorder_refined", "flow_name": scenario}},
        ]
        steps_map: Dict[int, Dict[str, str]] = {}
        for spec in specs:
            try:
                results = self.vector_db.query_where(spec["query"], spec["where"], top_k=top_k)
            except Exception:
                results = []
            for entry in results or []:
                meta = entry.get("metadata") or {}
                content = self._parse_content_snapshot(entry.get("content") or "")
                record_kind = (meta.get("record_kind") or (content or {}).get("record_kind") or "").lower()
                if record_kind == "element":
                    continue
                step_index = (content or {}).get("step_index") or meta.get("step_index")
                try:
                    step_index = int(step_index)
                except (TypeError, ValueError):
                    continue
                action = (content or {}).get("action") or meta.get("action") or ""
                navigation = (content or {}).get("navigation") or meta.get("navigation") or ""
                data_val = (content or {}).get("data") or meta.get("data") or ""
                expected = (content or {}).get("expected") or meta.get("expected") or ""
                if not any([action, navigation]):
                    continue
                steps_map.setdefault(
                    step_index,
                    {
                        "step": step_index,
                        "action": action,
                        "navigation": navigation,
                        "data": data_val,
                        "expected": expected,
                    },
                )
            if steps_map:
                break
        return [steps_map[idx] for idx in sorted(steps_map)]

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
        results = self.vector_db.query(scenario, top_k=top_k)
        assets: List[Dict[str, Any]] = []
        min_score = 6  # threshold to avoid unrelated matches
        scenario_tokens = self._tokenize(scenario)
        for entry in results:
            metadata = entry.get("metadata", {}) or {}
            meta_type = str(metadata.get("type", "")) + str(metadata.get("artifact_type", ""))
            if not any(token in meta_type.lower() for token in ["script", "scaffold", "locator", "page", "test"]):
                continue
            content_str = entry.get("content", "")
            path = self._locate_framework_file(framework, metadata, content_str)
            if path and path.exists():
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
        filtered = [(s, p) for s, p in candidates if s >= min_score]
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
        slug = _slugify(scenario)
        prompt = self.script_prompt.format(
            scenario=scenario,
            accepted_preview=accepted_preview,
            framework_summary=framework.summary(),
            locators_snippet=framework.sample_snippet(framework.locators_dir),
            pages_snippet=framework.sample_snippet(framework.pages_dir),
            tests_snippet=framework.sample_snippet(framework.tests_dir),
            slug=slug,
        )
        response = self.llm.invoke(prompt)
        raw = _strip_code_fences(getattr(response, "content", str(response)))
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"LLM did not return valid JSON: {exc}\nRaw output:\n{raw}") from exc

        for section in ["locators", "pages", "tests"]:
            payload.setdefault(section, [])
            if not isinstance(payload[section], list):
                raise ValueError(f"Payload section '{section}' must be a list")
            for file_obj in payload[section]:
                if "path" not in file_obj or "content" not in file_obj:
                    raise ValueError(f"Each file entry must include 'path' and 'content': {file_obj}")

        return payload

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
