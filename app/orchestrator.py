# orchestrator.py
import re
from pathlib import Path

from vector_db import VectorDBClient
from parser_utils import extract_structure, merge_recorder_flow, apply_ui_crawl_locators, insert_test_variations
from codegen_utils import generate_final_script
from executor import run_trial
from llm_client import ask_llm_for_script, ask_llm_to_self_heal, update_locator_cache


def safe_content(artifact):
    if artifact and isinstance(artifact, dict):
        return artifact.get("content")
    return None


class TestScriptOrchestrator:
    def __init__(self, db_path="./vector_store"):
        self.db = VectorDBClient(path=db_path)

    def _load_local_recorder_flow(self, identifier: str):
        flows_dir = Path("./app/saved_flows")
        if not flows_dir.exists():
            return None

        key = re.sub(r"[^a-zA-Z0-9]", "", (identifier or "").lower())
        candidates = sorted(flows_dir.glob("*.json"))
        fallback = None
        for path in candidates:
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            normalized_name = re.sub(r"[^a-zA-Z0-9]", "", path.stem.lower())
            context = {
                "content": content,
                "metadata": {
                    "source": "playwright-local",
                    "flow_name": path.stem,
                    "type": "recorder",
                },
            }
            if fallback is None:
                fallback = context
            if key and key not in normalized_name:
                continue
            return context
        return fallback

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

    def generate_and_run(self, test_case_id: str):
        existing_script, recorder_flow, ui_crawl, test_case, structure, enriched_steps = \
            self.generate_script(test_case_id)

        # Call LLM to generate new script
        new_script = ask_llm_for_script(
            structure=structure,
            existing_script=safe_content(existing_script),
            test_case=safe_content(test_case),
            enriched_steps=enriched_steps,
            ui_crawl=safe_content(ui_crawl),
        )

        # Trial run
        success, logs = run_trial(new_script)

        # Self-healing if locator fails
        if not success and "locator" in logs.lower():
            healed_script = ask_llm_to_self_heal(new_script, logs, safe_content(ui_crawl))
            success, logs = run_trial(healed_script)

            if success:
                new_script = healed_script

        return new_script, success, logs
