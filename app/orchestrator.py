"""Script orchestration that prefers local Playwright recordings over deprecated saved_flows."""
import json
import re
from pathlib import Path

from app.vector_db import VectorDBClient

try:
    from .parser_utils import (
        extract_structure,
        merge_recorder_flow,
        apply_ui_crawl_locators,
        insert_test_variations,
    )
except ImportError:  # pragma: no cover - fallback for direct execution
    from parser_utils import (  # type: ignore
        extract_structure,
        merge_recorder_flow,
        apply_ui_crawl_locators,
        insert_test_variations,
    )

try:
    from .codegen_utils import generate_final_script
except ImportError:  # pragma: no cover - fallback for direct execution
    from codegen_utils import generate_final_script  # type: ignore

try:
    from .executor import run_trial
except ImportError:  # pragma: no cover - fallback for direct execution
    from executor import run_trial  # type: ignore

try:
    from .llm_client import ask_llm_for_script, ask_llm_to_self_heal
except ImportError:  # pragma: no cover - fallback for direct execution
    from llm_client import ask_llm_for_script, ask_llm_to_self_heal  # type: ignore


def safe_content(artifact):
    if artifact and isinstance(artifact, dict):
        return artifact.get("content")
    return None


class TestScriptOrchestrator:
    def __init__(self, db_path="./vector_store"):
        self.db = VectorDBClient(path=db_path)

    def _load_local_recorder_flow(self, identifier: str):
        """Load newest recording metadata and convert to a simple steps JSON.

        We no longer use app/saved_flows/*.json. Instead, synthesize a steps array from
        recordings/<session>/metadata.json actions so downstream code can merge steps.
        """
        rec_dir = Path("./recordings")
        if not rec_dir.exists():
            return None

        key = re.sub(r"[^a-zA-Z0-9]", "", (identifier or "").lower())
        # Newest sessions first by metadata.json mtime
        candidates = []
        for sess in rec_dir.iterdir():
            if not sess.is_dir():
                continue
            meta = sess / "metadata.json"
            if meta.exists():
                try:
                    mtime = meta.stat().st_mtime
                except Exception:
                    mtime = 0
                candidates.append((mtime, sess.name, meta))
        candidates.sort(key=lambda t: t[0], reverse=True)
        if not candidates:
            return None

        def to_steps(meta_path: Path):
            try:
                data = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                return []
            steps = []
            for act in data.get("actions", []):
                action = (act.get("action") or act.get("type") or "").lower()
                if not action:
                    continue
                if action in ("navigate", "navigation"):
                    # Skip navigation; structure/harness will handle entry URL
                    continue
                elem = act.get("element") or {}
                selector = elem.get("cssPath") or elem.get("xpath") or "body"
                entry = {"action": action, "selector": selector}
                extra = act.get("extra") or {}
                if action in ("input", "change"):
                    entry["action"] = "fill"
                    value = extra.get("valueMasked") or extra.get("value") or elem.get("valueMasked") or ""
                    entry["value"] = value
                elif action == "press":
                    key = extra.get("key") or "Enter"
                    entry["key"] = key
                steps.append(entry)
            return steps

        for _mtime, sess_name, meta in candidates:
            steps = to_steps(meta)
            if not steps:
                continue
            content = json.dumps({"steps": steps}, ensure_ascii=False)
            context = {
                "content": content,
                "metadata": {
                    "source": "playwright-local",
                    "flow_name": sess_name,
                    "type": "recorder",
                },
            }
            normalized_name = re.sub(r"[^a-zA-Z0-9]", "", sess_name.lower())
            if key and key not in normalized_name:
                continue
            return context
        return None

    def generate_script(self, test_case_id: str):
        # 1️⃣ Fetch relevant artifacts
        results = self.db.query(test_case_id, top_k=10)

        # 2️⃣ Normalize results to a list of docs
        if isinstance(results, dict):
            docs = results.get("documents", [])
            ids = results.get("ids", [])
            metadatas = results.get("metadatas", [])
        elif isinstance(results, list):
            docs = []
            ids = []
            metadatas = []
            for item in results:
                if isinstance(item, dict):
                    docs.append(item.get("content"))
                    ids.append(item.get("id"))
                    metadatas.append(item.get("metadata", {}))
                else:
                    docs.append(item)
                    ids.append(None)
                    metadatas.append({})
        else:
            docs = []
            ids = []
            metadatas = []

        # 3️⃣ Build artifacts
        artifacts = []
        for idx, doc in enumerate(docs):
            artifacts.append({
                "id": ids[idx] if idx < len(ids) else None,
                "content": doc,
                "metadata": metadatas[idx] if idx < len(metadatas) else {}
            })

        # 4️⃣ Extract key artifacts
        existing_script = next((a for a in artifacts if a["metadata"].get("type") == "script"), None)
        recorder_flow   = next((a for a in artifacts if a["metadata"].get("type") == "recorder"), None)
        ui_crawl        = next((a for a in artifacts if a["metadata"].get("type") == "ui_crawl"), None)
        test_case       = next((a for a in artifacts if a["metadata"].get("type") == "test_case"), None)

        if not recorder_flow:
            local_flow = self._load_local_recorder_flow(test_case_id)
            if local_flow:
                recorder_flow = local_flow

        # 5️⃣ Process structure & steps
        structure = extract_structure(safe_content(existing_script)) if existing_script else {}
        steps = merge_recorder_flow(structure, safe_content(recorder_flow)) if recorder_flow else []
        steps = apply_ui_crawl_locators(steps, safe_content(ui_crawl)) if ui_crawl else steps
        enriched_steps = insert_test_variations(steps, safe_content(test_case)) if test_case else steps

        return existing_script, recorder_flow, ui_crawl, test_case, structure, enriched_steps

    # NOTE: A previous draft of a generate_and_run() helper leaked top-level code here,
    # which executed on import and caused 500 errors when importing this module.
    # That experimental block has been removed. If needed in the future, implement
    # a proper instance method like the sketch below and call it explicitly:
    #
    # def generate_and_run(self, test_case_id: str):
    #     existing_script, recorder_flow, ui_crawl, test_case, structure, enriched_steps = \
    #         self.generate_script(test_case_id)
    #     new_script = ask_llm_for_script(
    #         structure=structure,
    #         existing_script=safe_content(existing_script),
    #         test_case=safe_content(test_case),
    #         enriched_steps=enriched_steps,
    #         ui_crawl=safe_content(ui_crawl),
    #     )
    #     success, logs = run_trial(new_script)
    #     if not success and "locator" in logs.lower():
    #         healed_script = ask_llm_to_self_heal(new_script, logs, safe_content(ui_crawl))
    #         success, logs = run_trial(healed_script)
    #         if success:
    #             new_script = healed_script
    #     return new_script, success, logs
