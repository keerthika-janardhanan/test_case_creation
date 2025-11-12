from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends
import logging
from pydantic import BaseModel, Field
from ..auth import jwt_required
from ..framework_resolver import resolve_framework_root
from pathlib import Path
from ..sse import _format_sse
from starlette.responses import StreamingResponse
from typing import AsyncGenerator
import re
from ...trial_spec_adapter import trial_env_overrides


router = APIRouter(prefix="/agentic", tags=["agentic"])
logger = logging.getLogger(__name__)


class PreviewRequest(BaseModel):
    scenario: str


class PreviewResponse(BaseModel):
    preview: str


class RefineRequest(BaseModel):
    scenario: str
    previousPreview: str
    feedback: str


class PayloadRequest(BaseModel):
    scenario: str
    acceptedPreview: str


class FileItem(BaseModel):
    path: str
    content: str


class PayloadResponse(BaseModel):
    locators: list[FileItem]
    pages: list[FileItem]
    tests: list[FileItem]


def _unskip_tests_for_trial(source: str) -> tuple[str, int]:
    """Best-effort removal of declarative skips in test files for trial runs.

    We convert constructs like test.skip(name, fn) and test.describe.skip(name, fn)
    (and fixme variants) into active tests/blocks. This is applied ONLY for trial
    execution and never persisted to the repository.
    Returns (updated_source, replacements_count).
    """
    try:
        count = 0
        updated = source
        # 1) Replace describe-level skips/fixme at definition time
        for pat in (r"\btest\.describe\.skip\s*\(", r"\btest\.describe\.fixme\s*\("):
            updated, n = re.subn(pat, "test.describe(", updated)
            count += n
        # 2) Comment out runtime calls to test.skip()/test.fixme() inside bodies to avoid nested conversion
        def _comment_out_calls(src: str, name: str) -> tuple[str, int]:
            # Match start-of-line or after whitespace/semicolon until first closing paren and semicolon
            pattern = rf"(^|[;\s])test\.{name}\s*\([^;]*?\);"
            def repl(m: 're.Match[str]') -> str:
                prefix = m.group(1) or ""
                return prefix + f"// trial: removed test.{name}(...)"
            return re.subn(pattern, repl, src, flags=re.MULTILINE)
        updated, n1 = _comment_out_calls(updated, "skip")
        updated, n2 = _comment_out_calls(updated, "fixme")
        count += (n1 + n2)
        return updated, count
    except Exception:
        return source, 0


@router.post("/preview", response_model=PreviewResponse)
async def preview(req: PreviewRequest) -> PreviewResponse:
    try:
        from ...agentic_script_agent import AgenticScriptAgent, FrameworkProfile
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Import failure: {exc}") from exc

    framework_root = resolve_framework_root()
    framework = FrameworkProfile.from_root(framework_root)
    agent = AgenticScriptAgent()
    try:
        context = agent.gather_context(req.scenario)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Context gathering failed: {exc}") from exc
    try:
        preview_text = agent.generate_preview(req.scenario, framework, context)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Preview generation failed: {exc}") from exc
    return PreviewResponse(preview=preview_text)


@router.post("/refine", response_model=PreviewResponse)
async def refine(req: RefineRequest) -> PreviewResponse:
    try:
        from ...agentic_script_agent import AgenticScriptAgent, FrameworkProfile
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Import failure: {exc}") from exc
    framework_root = resolve_framework_root()
    framework = FrameworkProfile.from_root(framework_root)
    agent = AgenticScriptAgent()
    try:
        context = agent.gather_context(req.scenario)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Context gathering failed: {exc}") from exc
    try:
        refined_text = agent.refine_preview(req.scenario, framework, req.previousPreview, req.feedback, context)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Refine failed: {exc}") from exc
    return PreviewResponse(preview=refined_text)

@router.post("/payload", response_model=PayloadResponse)
async def payload(req: PayloadRequest) -> PayloadResponse:
    try:
        from ...agentic_script_agent import AgenticScriptAgent, FrameworkProfile
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Import failure: {exc}") from exc
    framework_root = resolve_framework_root()
    framework = FrameworkProfile.from_root(framework_root)
    agent = AgenticScriptAgent()
    payload_dict = agent.generate_script_payload(req.scenario, framework, req.acceptedPreview)
    return PayloadResponse(
        locators=[FileItem(**f) for f in payload_dict.get("locators", [])],
        pages=[FileItem(**f) for f in payload_dict.get("pages", [])],
        tests=[FileItem(**f) for f in payload_dict.get("tests", [])],
    )


@router.post("/preview/stream")
async def preview_stream(req: PreviewRequest) -> StreamingResponse:
    """Stream progress events while generating an agentic preview.

    Events payload shape (JSON per SSE data frame):
      { "phase": "start" | "gather_context" | "context_ready" | "preview" | "done" | "error", ... }
    """
    try:
        from ...agentic_script_agent import AgenticScriptAgent, FrameworkProfile
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Import failure: {exc}") from exc

    async def gen() -> AsyncGenerator[bytes, None]:
        try:
            yield _format_sse({"phase": "start"})
            framework_root = resolve_framework_root()
            framework = FrameworkProfile.from_root(framework_root)
            agent = AgenticScriptAgent()
            yield _format_sse({"phase": "gather_context"})
            context = agent.gather_context(req.scenario)
            flow_available = bool((context or {}).get("enriched_steps") or (context or {}).get("vector_steps"))
            yield _format_sse({"phase": "context_ready", "flow_available": flow_available})
            preview_text = agent.generate_preview(req.scenario, framework, context)
            yield _format_sse({"phase": "preview", "preview": preview_text})
            yield _format_sse({"phase": "done"})
        except Exception as exc:
            yield _format_sse({"phase": "error", "error": str(exc)})

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/payload/stream")
async def payload_stream(req: PayloadRequest) -> StreamingResponse:
    """Stream progress events while generating the agentic payload files.

    Event phases: start -> gather_context -> payload -> done (or error)
    """
    try:
        from ...agentic_script_agent import AgenticScriptAgent, FrameworkProfile
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Import failure: {exc}") from exc

    async def gen() -> AsyncGenerator[bytes, None]:
        try:
            yield _format_sse({"phase": "start"})
            framework_root = resolve_framework_root()
            framework = FrameworkProfile.from_root(framework_root)
            agent = AgenticScriptAgent()
            yield _format_sse({"phase": "gather_context"})
            context = agent.gather_context(req.scenario)
            yield _format_sse({"phase": "context_ready", "flow_available": bool(context.get("vector_steps"))})
            payload_dict = agent.generate_script_payload(req.scenario, framework, req.acceptedPreview)
            # Only emit brief shapes to keep frames small
            summary = {
                "locators": len(payload_dict.get("locators", [])),
                "pages": len(payload_dict.get("pages", [])),
                "tests": len(payload_dict.get("tests", [])),
            }
            yield _format_sse({"phase": "payload", "summary": summary})
            yield _format_sse({"phase": "done"})
        except Exception as exc:
            yield _format_sse({"phase": "error", "error": str(exc)})

    return StreamingResponse(gen(), media_type="text/event-stream")


class PersistRequest(BaseModel):
    files: list[FileItem]
    frameworkRoot: str | None = None


@router.post("/persist", dependencies=[Depends(jwt_required)])
async def persist(req: PersistRequest) -> dict:
    try:
        from ...agentic_script_agent import AgenticScriptAgent, FrameworkProfile
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Import failure: {exc}") from exc
    # Resolve provided frameworkRoot via shared resolver (supports remote URLs)
    framework_root = resolve_framework_root(req.frameworkRoot) if req.frameworkRoot else resolve_framework_root()
    framework = FrameworkProfile.from_root(framework_root)
    agent = AgenticScriptAgent()
    payload = {"locators": [], "pages": [], "tests": []}
    for f in req.files:
        # Group files by top-level folder name (locators/pages/tests)
        folder = (f.path.split("/")[0] or "").lower()
        if folder in payload:
            payload[folder].append({"path": f.path, "content": f.content})
        else:
            # default to tests if unknown
            payload["tests"].append({"path": f.path, "content": f.content})
    written = agent.persist_payload(framework, payload)
    rels = [str(p.relative_to(framework.root)).replace('\\', '/') for p in written]
    return {"written": rels}


class PushRequest(BaseModel):
    branch: str = Field("feature/agentic")
    message: str = Field("Add generated Playwright test")
    frameworkRoot: str | None = None


@router.post("/push", dependencies=[Depends(jwt_required)])
async def push(req: PushRequest) -> dict:
    try:
        from ...agentic_script_agent import AgenticScriptAgent, FrameworkProfile
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Import failure: {exc}") from exc
    # Resolve provided frameworkRoot via shared resolver (supports remote URLs)
    framework_root = resolve_framework_root(req.frameworkRoot) if req.frameworkRoot else resolve_framework_root()
    framework = FrameworkProfile.from_root(framework_root)
    agent = AgenticScriptAgent()
    ok = agent.push_changes(framework, branch=req.branch, commit_msg=req.message)
    return {"success": bool(ok)}


class TrialRunRequest(BaseModel):
    testFileContent: str
    headed: bool = Field(True, description="Run browser in headed mode (defaults to true).")
    frameworkRoot: str | None = Field(None, description="Optional framework root to place temp spec inside tests dir")
    # Optional: before running, update testmanager.xlsx for this scenario
    scenario: str | None = Field(None, description="Scenario/TestCase identifier to enable in testmanager.xlsx")
    updateTestManager: bool = Field(False, description="If true and scenario provided, set Execute='Yes' and update datasheet mapping")
    datasheet: str | None = Field(None, description="Datasheet file name to write into testmanager.xlsx (optional)")
    referenceId: str | None = Field(None, description="ReferenceID value to write into testmanager.xlsx (optional)")
    idName: str | None = Field(None, description="IDName (column name) to write into testmanager.xlsx (optional)")


class TrialRunResponse(BaseModel):
    success: bool
    logs: str
    updateInfo: dict | None = None


@router.post("/trial-run", response_model=TrialRunResponse)
async def trial_run(req: TrialRunRequest) -> TrialRunResponse:
    """Execute a temporary Playwright test file. If frameworkRoot provided, place spec inside its tests dir to honor config."""
    try:
        from ...executor import run_trial, run_trial_in_framework
        from ..framework_resolver import resolve_framework_root
        from pathlib import Path as _P
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Import failure: {exc}") from exc

    upd_info = None
    if req.frameworkRoot:
        try:
            # Allow remote git URLs by delegating to resolver first
            try:
                root = resolve_framework_root(req.frameworkRoot)
            except Exception:
                # Fallback to local path resolution if it's not a URL or resolver failed
                root = _P(req.frameworkRoot).expanduser().resolve()
            if not root.exists():
                raise HTTPException(status_code=404, detail=f"frameworkRoot not found: {root}")
            # Optionally update testmanager.xlsx prior to running the trial
            if req.updateTestManager and (req.scenario or "").strip():
                try:
                    from ...services.config_service import update_test_manager_entry as _upd
                    upd = _upd(
                        root,
                        scenario=(req.scenario or "").strip(),
                        execute_value="Yes",
                        create_if_missing=True,
                        datasheet=(req.datasheet or None),
                        reference_id=(req.referenceId or None),
                        id_name=(req.idName or None),
                    )
                    upd_info = upd or None
                    if not upd:
                        # testmanager.xlsx missing or invalid
                        raise HTTPException(status_code=404, detail="testmanager.xlsx not found or invalid")
                except HTTPException:
                    raise
                except Exception as exc:
                    raise HTTPException(status_code=500, detail=f"Failed updating testmanager.xlsx: {exc}") from exc

            # Auto-create minimal stubs for missing page object imports to prevent module not found errors
            try:
                missing_created = []
                # Find import lines like: import X from "../pages/SomePage.ts";
                pattern = re.compile(r'import\s+[^;]*?from\s+"(\.\./pages/[^"\n]+\.ts)"')
                for match in pattern.finditer(req.testFileContent):
                    rel_path = match.group(1)
                    target_path = (root / rel_path).resolve()
                    # Security: ensure within root
                    try:
                        target_path.relative_to(root)
                    except ValueError:
                        continue
                    if not target_path.exists():
                        target_path.parent.mkdir(parents=True, exist_ok=True)
                        # Derive class/interface name crudely from filename
                        base_name = target_path.stem
                        class_name = re.sub(r'[^A-Za-z0-9]', '', base_name.title()) or 'PageObject'
                        stub = (
                            f"// Auto-generated stub to unblock trial run for {base_name}\n"
                            f"export default class {class_name} {{\n"
                            f"  constructor(page) {{ this.page = page; }}\n"
                            f"  async placeholder() {{ /* implement actions */ }}\n"
                            f"}}\n"
                        )
                        try:
                            target_path.write_text(stub, encoding='utf-8')
                            missing_created.append(str(target_path.relative_to(root)))
                        except Exception:
                            pass
                # Optionally could log created stubs; for now silent
            except Exception:
                pass
            # Temporarily unskip tests for trial runs only (not persisted)
            content, replaced = _unskip_tests_for_trial(req.testFileContent)
            env_overrides = trial_env_overrides(root, case_id=(req.scenario or None))
            # Compose a non-sensitive banner indicating chosen trial credentials
            def _mask_pw(pw: str | None) -> str:
                if not pw:
                    return ""
                if len(pw) <= 2:
                    return "***"
                return ("*" * (len(pw) - 2)) + pw[-2:]
            user = env_overrides.get("USERID") or env_overrides.get("USERNAME") or env_overrides.get("TRIAL_USERNAME") or env_overrides.get("EMAIL") or ""
            pw = env_overrides.get("PASSWORD") or env_overrides.get("TRIAL_PASSWORD") or ""
            base = env_overrides.get("BASE_URL") or env_overrides.get("URL") or env_overrides.get("TRIAL_BASE_URL") or env_overrides.get("TRIAL_URL") or ""
            banner = "[trial-creds] username=" + (user or "<empty>") + ", password=" + _mask_pw(pw) + (", base_url=" + base if base else "") + "\n"
            success, logs = run_trial_in_framework(content, root, headed=req.headed, env_overrides=env_overrides)
            logger.info(banner.strip())
            logs = banner + logs
            if replaced:
                logs = f"[trial-note] Unskipped {replaced} skipped/fixme declarations for this run.\n" + logs
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Framework trial failure: {exc}") from exc
    else:
        content, replaced = _unskip_tests_for_trial(req.testFileContent)
        # Use resolved framework root (default) for credentials fallback; safe if not present
        default_root = resolve_framework_root()
        env_overrides = trial_env_overrides(default_root, case_id=(req.scenario or None))
        def _mask_pw(pw: str | None) -> str:
            if not pw:
                return ""
            if len(pw) <= 2:
                return "***"
            return ("*" * (len(pw) - 2)) + pw[-2:]
        user = env_overrides.get("USERID") or env_overrides.get("USERNAME") or env_overrides.get("TRIAL_USERNAME") or env_overrides.get("EMAIL") or ""
        pw = env_overrides.get("PASSWORD") or env_overrides.get("TRIAL_PASSWORD") or ""
        base = env_overrides.get("BASE_URL") or env_overrides.get("URL") or env_overrides.get("TRIAL_BASE_URL") or env_overrides.get("TRIAL_URL") or ""
        banner = "[trial-creds] username=" + (user or "<empty>") + ", password=" + _mask_pw(pw) + (", base_url=" + base if base else "") + "\n"
        success, logs = run_trial(content, headed=req.headed, env_overrides=env_overrides)
        logger.info(banner.strip())
        logs = banner + logs
        if replaced:
            logs = f"[trial-note] Unskipped {replaced} skipped/fixme declarations for this run.\n" + logs
    return TrialRunResponse(success=bool(success), logs=logs, updateInfo=upd_info)


class TrialRunExistingRequest(BaseModel):
    testFilePath: str = Field(..., description="Relative path to existing test file inside framework repo")
    headed: bool = Field(True)
    frameworkRoot: str | None = Field(None, description="Optional explicit framework root; auto-resolved if omitted")
    # Optional: update testmanager before running
    scenario: str | None = Field(None, description="Scenario/TestCase identifier to enable in testmanager.xlsx")
    updateTestManager: bool = Field(False, description="If true and scenario provided, set Execute='Yes' and update datasheet mapping")
    datasheet: str | None = Field(None, description="Datasheet file name to write into testmanager.xlsx (optional)")
    referenceId: str | None = Field(None, description="ReferenceID value to write into testmanager.xlsx (optional)")
    idName: str | None = Field(None, description="IDName (column name) to write into testmanager.xlsx (optional)")


@router.post("/trial-run-existing", response_model=TrialRunResponse)
async def trial_run_existing(req: TrialRunExistingRequest) -> TrialRunResponse:
    """Execute an existing test file from the framework repository.

    Reads the file content and delegates to run_trial (temp spec execution) so we don't mutate repo.
    """
    try:
        from ...executor import run_trial_in_framework
        from ..framework_resolver import resolve_framework_root
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Import failure: {exc}") from exc
    # Resolve provided frameworkRoot via shared resolver (supports remote URLs)
    root = resolve_framework_root(req.frameworkRoot) if req.frameworkRoot else resolve_framework_root()
    # Optionally update testmanager.xlsx prior to running the trial
    upd_info = None
    if req.updateTestManager and (req.scenario or "").strip():
        try:
            from ...services.config_service import update_test_manager_entry as _upd
            upd_info = _upd(
                root,
                scenario=(req.scenario or "").strip(),
                execute_value="Yes",
                create_if_missing=True,
                datasheet=(req.datasheet or None),
                reference_id=(req.referenceId or None),
                id_name=(req.idName or None),
            )
        except Exception:
            # Non-fatal: proceed with trial even if update fails
            pass
    target = (root / req.testFilePath).resolve()
    try:
        if target.is_dir():
            raise HTTPException(status_code=400, detail="testFilePath points to a directory")
        if not target.exists():
            raise HTTPException(status_code=404, detail=f"Test file not found: {req.testFilePath}")
        # Prevent path escape
        root_resolved = root.resolve()
        if root_resolved not in target.parents and target != root_resolved:
            raise HTTPException(status_code=400, detail="testFilePath escapes framework root")
        content = target.read_text(encoding="utf-8", errors="replace")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed reading file: {exc}") from exc
    # Execute inside framework root so its Playwright config and node_modules apply.
    # Temporarily unskip tests for trial runs only
    content2, replaced = _unskip_tests_for_trial(content)
    env_overrides = trial_env_overrides(root, case_id=(req.scenario or None), spec_path=target)
    def _mask_pw(pw: str | None) -> str:
        if not pw:
            return ""
        if len(pw) <= 2:
            return "***"
        return ("*" * (len(pw) - 2)) + pw[-2:]
    user = env_overrides.get("USERID") or env_overrides.get("USERNAME") or env_overrides.get("TRIAL_USERNAME") or env_overrides.get("EMAIL") or ""
    pw = env_overrides.get("PASSWORD") or env_overrides.get("TRIAL_PASSWORD") or ""
    base = env_overrides.get("BASE_URL") or env_overrides.get("URL") or env_overrides.get("TRIAL_BASE_URL") or env_overrides.get("TRIAL_URL") or ""
    banner = "[trial-creds] username=" + (user or "<empty>") + ", password=" + _mask_pw(pw) + (", base_url=" + base if base else "") + "\n"
    success, logs = run_trial_in_framework(content2, root, headed=req.headed, env_overrides=env_overrides)
    logger.info(banner.strip())
    logs = banner + logs
    if replaced:
        logs = f"[trial-note] Unskipped {replaced} skipped/fixme declarations for this run.\n" + logs
    return TrialRunResponse(success=bool(success), logs=logs, updateInfo=upd_info)


class KeywordInspectRequest(BaseModel):
    keyword: str = Field(..., description="Scenario keyword to inspect against repo and refined recorder flows")
    repoPath: str = Field(..., description="Framework repository path or git URL")
    branch: str | None = Field(None, description="Branch to use (optional if embedded in URL)")
    maxAssets: int = Field(5, ge=1, le=25, description="Maximum existing framework assets to return")


class ExistingAsset(BaseModel):
    path: str
    snippet: str
    isTest: bool = False
    relevance: int | None = None


class RefinedRecorderFlow(BaseModel):
    sourceSession: str | None = None
    steps: list[dict] = []
    stabilityWarnings: list[str] = []


class VectorContext(BaseModel):
    flowAvailable: bool
    vectorStepsCount: int


class KeywordInspectResponse(BaseModel):
    keyword: str
    existingAssets: list[ExistingAsset]
    refinedRecorderFlow: RefinedRecorderFlow | None
    vectorContext: VectorContext
    status: str
    messages: list[str]


@router.post("/keyword-inspect", response_model=KeywordInspectResponse)
async def keyword_inspect(req: KeywordInspectRequest) -> KeywordInspectResponse:
    """Inspect a keyword against the framework repo and refined recorder/vector flows.

    Resolution order:
      1. Validate repo path (clone if remote) using existing resolve logic.
      2. Use AgenticScriptAgent.find_existing_framework_assets to locate matching files.
      3. Use AgenticScriptAgent.gather_context to obtain vector/refined steps.
      4. Summarise results and return structured response.
    """
    try:
        from ...agentic_script_agent import AgenticScriptAgent, FrameworkProfile
        from ..framework_resolver import resolve_framework_root
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Import failure: {exc}") from exc

    # Pre-validate simple fields outside catch-all so 400s are preserved
    keyword = (req.keyword or "").strip()
    if not keyword:
        raise HTTPException(status_code=400, detail="Keyword is required")
    repo_input = (req.repoPath or "").strip()
    if not repo_input:
        raise HTTPException(status_code=400, detail="repoPath is mandatory")

    # Lightweight normalization similar to streamlit_app normalize_remote_repo_input
    def _normalize_remote_repo_input(raw: str) -> tuple[str, str | None]:
        cleaned = raw.replace("\\", "/").strip()
        cleaned = cleaned.replace("https:/", "https://").replace("http:/", "http://")
        branch_in_url = None
        if cleaned.startswith("git@"):
            return cleaned, branch_in_url
        if "://" not in cleaned and cleaned.startswith("github.com"):
            cleaned = f"https://{cleaned}"
        if cleaned.startswith("http") and "/tree/" in cleaned:
            base, remainder = cleaned.split("/tree/", 1)
            branch_in_url = remainder.split("/", 1)[0]
            cleaned = base
        if cleaned.endswith("/"):
            cleaned = cleaned[:-1]
        if cleaned.startswith("http") and not cleaned.endswith(".git"):
            cleaned = f"{cleaned}.git"
        return cleaned, branch_in_url

    # Catch-all to avoid leaking 500s; keep 400s by re-raising HTTPException
    try:
        desired_branch = (req.branch or "").strip()
        framework_root: Path
        active_branch = desired_branch or ""

        # Use shared resolver to normalize local path or clone remote URL consistently
        try:
            framework_root = resolve_framework_root(repo_input)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Unable to resolve repository: {exc}") from exc

        framework = FrameworkProfile.from_root(framework_root)
        agent = AgenticScriptAgent()

        # Existing assets search
        existing_assets_raw = []
        try:
            existing_assets_raw = agent.find_existing_framework_assets(keyword, framework, top_k=req.maxAssets)
        except Exception:
            existing_assets_raw = []

        existing_assets: list[ExistingAsset] = []
        for asset in existing_assets_raw:
            path_obj = asset.get("path")
            if not path_obj:
                continue
            try:
                content = path_obj.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                content = ""
            snippet = "\n".join(content.splitlines()[:40])
            try:
                rel_path = str(path_obj.relative_to(framework.root)).replace("\\", "/")
            except Exception:
                # Fallback if the file isn't strictly under root (defensive)
                rel_path = str(path_obj).replace("\\", "/")
            is_test = rel_path.lower().startswith("tests/") or rel_path.lower().endswith(".spec.ts")
            relevance = (asset.get("metadata") or {}).get("relevance_score")
            existing_assets.append(ExistingAsset(path=rel_path, snippet=snippet, isTest=is_test, relevance=relevance))

        # Gather context (vector/refined steps) but avoid failing the whole endpoint
        try:
            context = agent.gather_context(keyword)
        except Exception:
            context = {"vector_steps": [], "flow_available": False}

        vector_steps = context.get("vector_steps") or []
        flow_available = bool(context.get("flow_available"))

        refined_flow_steps = []
        if vector_steps:
            for step in vector_steps:
                refined_flow_steps.append({
                    "step": step.get("step"),
                    "action": step.get("action"),
                    "navigation": step.get("navigation"),
                    "data": step.get("data"),
                    "expected": step.get("expected"),
                })

        refined_flow = None
        stability_warnings: list[str] = []
        for s in refined_flow_steps:
            if not s.get("action") and not s.get("navigation"):
                stability_warnings.append(f"Step {s.get('step')} missing action/navigation")

        if refined_flow_steps:
            flow_info = context.get("vector_flow") or {}
            source_session = flow_info.get("flow_name") if isinstance(flow_info, dict) else None
            refined_flow = RefinedRecorderFlow(sourceSession=source_session, steps=refined_flow_steps, stabilityWarnings=stability_warnings)

        status: str
        messages: list[str] = []
        if existing_assets and refined_flow:
            status = "found-existing"
            messages.append("Existing framework assets and refined recorder flow found")
        elif existing_assets:
            status = "found-existing"
            messages.append("Existing framework assets found")
        elif refined_flow:
            status = "found-refined-only"
            messages.append("Refined recorder/vector flow found")
        else:
            status = "none"
            messages.append("No information available in repo or refined flows")

        return KeywordInspectResponse(
            keyword=keyword,
            existingAssets=existing_assets,
            refinedRecorderFlow=refined_flow,
            vectorContext=VectorContext(flowAvailable=flow_available, vectorStepsCount=len(vector_steps)),
            status=status,
            messages=messages,
        )
    except HTTPException:
        # Preserve intended HTTP status for validation/git errors
        raise
    except Exception as fatal_exc:
        # Final catch-all: return structured error response instead of 500
        return KeywordInspectResponse(
            keyword=(req.keyword or "").strip(),
            existingAssets=[],
            refinedRecorderFlow=None,
            vectorContext=VectorContext(flowAvailable=False, vectorStepsCount=0),
            status="error",
            messages=[f"keyword-inspect failed: {type(fatal_exc).__name__}: {fatal_exc}"],
        )

@router.post("/trial-run/stream")
async def trial_run_stream(req: TrialRunRequest) -> StreamingResponse:
    """Stream real-time execution logs of a temporary Playwright test via SSE.

    Phases: start -> running -> chunk (repeated) -> done OR error
    Each chunk frame contains {"phase": "chunk", "data": "..."}
    Final frame includes {"phase": "done", "success": bool}
    """
    try:
        import asyncio
        import tempfile, os, subprocess
        from pathlib import Path as _P
        from ...executor import _resolve_playwright_command, _detect_test_dir
        from ..framework_resolver import resolve_framework_root as _resolve_root
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Import failure: {exc}") from exc

    async def gen() -> AsyncGenerator[bytes, None]:
        try:
            yield _format_sse({"phase": "start"})
            tmp_path = None
            cwd = None
            cmd = None
            # If a frameworkRoot is specified, write inside its detected testDir so Playwright config applies.
            if req.frameworkRoot:
                try:
                    # Resolve local path or remote git URL consistently
                    root = _resolve_root(req.frameworkRoot)
                except Exception as exc:
                    yield _format_sse({"phase": "error", "error": f"Unable to resolve frameworkRoot: {exc}"})
                    return
                # Optional testmanager update prior to run
                if req.updateTestManager and (req.scenario or "").strip():
                    try:
                        from ...services.config_service import update_test_manager_entry as _upd
                        upd = _upd(
                            root,
                            scenario=(req.scenario or "").strip(),
                            execute_value="Yes",
                            create_if_missing=True,
                            datasheet=(req.datasheet or None),
                            reference_id=(req.referenceId or None),
                            id_name=(req.idName or None),
                        )
                        if upd:
                            yield _format_sse({"phase": "update", "update": upd})
                    except Exception:
                        pass
                test_dir = _detect_test_dir(root)
                test_dir.mkdir(parents=True, exist_ok=True)
                # Unskip for trial stream as well
                content, replaced = _unskip_tests_for_trial(req.testFileContent)
                with tempfile.NamedTemporaryFile(delete=False, suffix=".spec.ts", dir=str(test_dir)) as tmp:
                    tmp.write(content.encode("utf-8"))
                    tmp_path = tmp.name
                # Use path relative to framework root to avoid Windows path regex pitfalls
                try:
                    rel = _P(tmp_path).relative_to(root).as_posix()
                except ValueError:
                    rel = tmp_path.replace('\\', '/')
                cmd, cwd = _resolve_playwright_command(rel, req.headed, project_root=root)
                yield _format_sse({"phase": "prepared", "headed": req.headed, "cmd": cmd, "cwd": cwd, "unskipped": replaced})
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    cwd=str(root),
                )
            else:
                # Write temp spec file in system temp; rely on global PW config
                content, replaced = _unskip_tests_for_trial(req.testFileContent)
                with tempfile.NamedTemporaryFile(delete=False, suffix=".spec.ts") as tmp:
                    tmp.write(content.encode("utf-8"))
                    tmp_path = tmp.name
                cmd, cwd = _resolve_playwright_command(tmp_path, req.headed)
                yield _format_sse({"phase": "prepared", "headed": req.headed, "cmd": cmd, "cwd": cwd, "unskipped": replaced})
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    cwd=cwd,
                )

            yield _format_sse({"phase": "running"})
            assert proc.stdout is not None
            while True:
                line = await asyncio.get_event_loop().run_in_executor(None, proc.stdout.readline)
                if not line:
                    break
                yield _format_sse({"phase": "chunk", "data": line.rstrip()})
            ret = proc.wait()
            success = ret == 0
            yield _format_sse({"phase": "done", "success": success})
        except Exception as exc:
            yield _format_sse({"phase": "error", "error": str(exc)})
        finally:  # cleanup
            try:
                if 'tmp_path' in locals() and tmp_path and os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            except OSError:
                pass

    return StreamingResponse(gen(), media_type="text/event-stream")
