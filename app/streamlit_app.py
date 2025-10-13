# streamlit_app.py
import os
import io
import json
import subprocess
import sys
import signal
import time
import hashlib
import pandas as pd
import streamlit as st
from urllib.parse import urlparse
from hashstore import init_db
from vector_db import VectorDBClient
from test_case_generator import TestCaseGenerator, map_llm_to_template
from ingest_utils import ingest_artifact
from ingest import ingest_jira, ingest_web_site, ingest_ui_crawl, ingest_document
from parse_playwright import parse_playwright_code
from locator_generator import generate_xpath_candidates, to_union_xpath
from recorder_enricher import enrich_recorder_flow, persist_enriched_artifacts
from template_utils import load_excel_template
import tempfile
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
# from langchain.chat_models import ChatOpenAI
from codegen_utils import generate_final_script
from executor import run_trial
from agentic_script_agent import (
    AgenticScriptAgent,
    FrameworkProfile,
    initialise_agentic_state,
    interpret_confirmation,
    interpret_feedback,
    interpret_push,
)

# -------------------------- Constants --------------------------
JSON_FLOW_DIR = os.path.join(os.getcwd(), "app", "saved_flows")
LOCATOR_DIR = os.path.join(os.getcwd(), "app", "./locators")
os.makedirs(JSON_FLOW_DIR, exist_ok=True)
os.makedirs("uploads", exist_ok=True)
FRAMEWORK_CLONE_BASE = Path(os.getcwd()) / "framework_repos"
FRAMEWORK_CLONE_BASE.mkdir(exist_ok=True)

# -------------------------- Initialize DB & Vector --------------------------
init_db()
db = VectorDBClient()
agentic_engine = AgenticScriptAgent()

# -------------------------- Page Config --------------------------
st.set_page_config(page_title="Test Artifact Recorder & Ingest", layout="wide")

# -------------------------- Authentication (demo) --------------------------
if "role" not in st.session_state:
    st.session_state["role"] = "user"

if "agentic_state" not in st.session_state:
    st.session_state.agentic_state = initialise_agentic_state()

st.session_state.setdefault("framework_repo_path", "")
st.session_state.setdefault("framework_branch", "main")
st.session_state.setdefault("framework_commit_message", "Add generated Playwright test")
st.session_state.setdefault("resolved_framework_path", "")

st.sidebar.header("Login (demo)")
st.session_state["role"] = st.sidebar.selectbox(
    "Select role", ["user", "admin"], index=0, key="role_select"
)

st.sidebar.markdown("---")
st.sidebar.subheader("Agentic Script Settings")
st.session_state.framework_repo_path = st.sidebar.text_input(
    "Framework Repo Path",
    value=st.session_state.framework_repo_path,
    key="framework_repo_path_input",
)
st.session_state.framework_branch = st.sidebar.text_input(
    "Git Branch",
    value=st.session_state.framework_branch,
    key="framework_branch_input",
)
st.session_state.framework_commit_message = st.sidebar.text_input(
    "Commit Message",
    value=st.session_state.framework_commit_message,
    key="framework_commit_message_input",
)
st.session_state.setdefault("rec_python_executable", sys.executable)
st.session_state.rec_python_executable = st.sidebar.text_input(
    "Recorder Python Executable",
    value=st.session_state.rec_python_executable,
    help="Optional path to the Python executable used to launch the recorder (defaults to Streamlit's Python).",
    key="rec_python_executable_input",
)

st.title("Test Artifact Recorder & Ingest")

# -------------------------- Helper: Flatten Metadata --------------------------
def flatten_metadata(meta: dict) -> dict:
    """Flatten metadata and remove None values for Chroma compatibility."""
    flat = {}
    for k, v in meta.items():
        if v is None:
            continue
        elif isinstance(v, (dict, list)):
            flat[k] = json.dumps(v, ensure_ascii=False)
        else:
            flat[k] = v
    return flat

# -------------------------- Admin Panel --------------------------
if st.session_state["role"] == "admin":
    st.header("Admin: Ingest & Manage")

    # ---------------- Jira ----------------
    st.subheader("Jira Ingestion")
    jql_input = st.text_input(
        "Jira JQL",
        value="project=GEN_AI_PROJECT ORDER BY created DESC",
        key="jira_jql_input"
    )
    if st.button("Fetch & Ingest Jira", key="btn_ingest_jira"):
        try:
            results = ingest_jira(jql_input)
            st.success(f"Jira stories ingested: {len(results)} issues ✅")
        except Exception as e:
            st.error(f"Jira ingestion failed: {e}")

    # ---------------- Website ----------------
    st.subheader("Website Ingestion")
    url = st.text_input(
        "Website URL",
        value="https://docs.oracle.com/en/cloud/saas/index.html",
        key="website_url_input"
    )
    max_depth = st.number_input(
        "Max Depth", min_value=1, max_value=5, value=2, key="website_max_depth"
    )
    if st.button("Fetch & Ingest Website", key="btn_ingest_website"):
        if url.strip():
            try:
                with st.spinner(f"Crawling {url} up to depth {max_depth}..."):
                    results = ingest_web_site(url, max_depth)
                st.success(f"Website ingestion finished: {len(results)} docs added ✅")
            except Exception as e:
                st.error(f"Website ingestion failed: {e}")
        else:
            st.warning("Please enter a valid URL")

    # ---------------- Document Ingestion ----------------
    st.subheader("Document Ingestion")
    uploaded_files = st.file_uploader(
        "Upload documents (PDF, DOCX, TXT)",
        type=["pdf", "docx", "doc", "txt"],
        accept_multiple_files=True,
        key="doc_uploader"
    )

    if uploaded_files:
        if st.button("Ingest Uploaded Documents", key="btn_ingest_docs"):
            all_results = []
            try:
                for uploaded_file in uploaded_files:
                    temp_path = os.path.join("uploads", uploaded_file.name)
                    with open(temp_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                    with st.spinner(f"Ingesting {uploaded_file.name}..."):
                        results = ingest_document(temp_path)
                        all_results.extend(results)
                st.success(f"Document ingestion finished: {len(all_results)} docs added ✅")
            except Exception as e:
                st.error(f"Document ingestion failed: {e}")

    # ---------------- UI Crawl ----------------
    st.subheader("UI Crawl Ingestion")
    crawl_file = st.file_uploader(
        "Upload crawl JSON", type=["json"], key="crawl_file_uploader"
    )
    if st.button("Ingest UI Crawl", key="btn_ingest_ui_crawl"):
        if crawl_file:
            path = f"./uploads/{crawl_file.name}"
            with open(path, "wb") as f:
                f.write(crawl_file.getbuffer())
            try:
                results = ingest_ui_crawl(path)
                st.success(f"UI Crawl ingested: {len(results)} flows ✅")
            except Exception as e:
                st.error(f"UI Crawl ingestion failed: {e}")
        else:
            st.warning("Please upload a crawl JSON file")

    # ---------------- Delete Management ----------------
    st.subheader("Manage Vector DB Documents")
    delete_mode = st.radio(
        "Choose delete mode", ["By ID", "By Source"], key="delete_mode_radio"
    )
    
    if delete_mode == "By ID":
        doc_id_input = st.text_input("Enter Document ID to delete", key="delete_doc_id")
        if st.button("🗑️ Delete Document by ID", key="btn_delete_by_id"):
            if doc_id_input.strip():
                try:
                    db.delete_document(doc_id_input.strip())
                    st.success(f"Document '{doc_id_input}' deleted successfully ✅")
                except Exception as e:
                    st.error(f"Failed to delete document: {e}")
            else:
                st.warning("Please enter a valid Document ID.")
    
    elif delete_mode == "By Source":
        source_input = st.text_input("Enter Source (e.g. 'jira', 'ui_flow')", key="delete_source_input")
        if st.button("🗑️ Delete All Documents by Source", key="btn_delete_by_source"):
            if source_input.strip():
                try:
                    db.delete_by_source(source_input.strip())
                    st.success(f"All documents from source '{source_input}' deleted ✅")
                except Exception as e:
                    st.error(f"Failed to delete by source: {e}")
            else:
                st.warning("Please enter a valid source name.")

    # ---------------- Show Existing Docs ----------------
    if st.checkbox("📋 Show Existing Docs with Pagination", key="show_docs_checkbox"):
        try:
            all_docs = db.list_all(limit=1000)
            if all_docs:
                page_size = st.number_input("Docs per page", min_value=5, max_value=100, value=20, key="docs_page_size")
                total_pages = (len(all_docs) + page_size - 1) // page_size
                current_page = st.number_input("Page", min_value=1, max_value=total_pages, value=1, key="docs_page_num")

                start_idx = (current_page - 1) * page_size
                end_idx = start_idx + page_size
                page_docs = all_docs[start_idx:end_idx]

                df = pd.DataFrame(page_docs)
                st.dataframe(df)

                st.write(f"Showing page {current_page} of {total_pages}")
            else:
                st.info("No documents found in Vector DB.")
        except Exception as e:
            st.error(f"Failed to fetch documents: {e}")

# -------------------------- Playwright Recorder Panel --------------------------
st.header("Playwright Recorder → Vector DB Ingestion")
flow_name = st.text_input("Flow Name", "playwright-recorded-flow")
record_url = st.text_input("URL to Record", "https://example.com")

if "record_proc" not in st.session_state:
    st.session_state["record_proc"] = None
if "record_session_dir" not in st.session_state:
    st.session_state["record_session_dir"] = None
if "record_metadata" not in st.session_state:
    st.session_state["record_metadata"] = None
if "record_manual_out_path" not in st.session_state:
    st.session_state["record_manual_out_path"] = None
if "record_manual_log" not in st.session_state:
    st.session_state["record_manual_log"] = ""
if "record_session_listing" not in st.session_state:
    st.session_state["record_session_listing"] = None


def _load_recorder_metadata(session_dir: str, attempts: int = 15, delay: float = 0.5) -> Optional[dict]:
    session_path = Path(session_dir)
    metadata_path = session_path / "metadata.json"
    for _ in range(attempts):
        if metadata_path.exists():
            try:
                return json.loads(metadata_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                time.sleep(delay)
                continue
        time.sleep(delay)
    return None


def _scan_session_directory(session_dir: str) -> Dict[str, Any]:
    session_path = Path(session_dir)
    summary: Dict[str, Any] = {
        "exists": session_path.exists(),
        "top_level": [],
        "dom_files": 0,
        "screenshot_files": 0,
    }
    if not session_path.exists():
        return summary
    try:
        summary["top_level"] = sorted(p.name for p in session_path.iterdir())
    except Exception:
        summary["top_level"] = []
    dom_dir = session_path / "dom"
    if dom_dir.exists():
        summary["dom_files"] = len(list(dom_dir.glob("*.html")))
    shots_dir = session_path / "screenshots"
    if shots_dir.exists():
        summary["screenshot_files"] = len(list(shots_dir.glob("*.png")))
    return summary


def _normalize_record_url(raw_url: str) -> Tuple[Optional[str], Optional[str]]:
    """Return a sanitized http(s) URL suitable for the recorder command."""

    url = (raw_url or "").strip()
    if not url:
        return None, "Please enter a URL to record."

    if "://" not in url:
        url = f"https://{url}"

    parsed = urlparse(url)
    if not parsed.netloc:
        return None, "The recording URL must include a valid host name."

    if parsed.scheme.lower() not in {"http", "https"}:
        return None, "Only http and https URLs are supported for recording."

    normalized = parsed.geturl()
    return normalized, None


def _validate_recorder_runtime(python_exec: str) -> Optional[str]:
    """Ensure the selected interpreter can launch the recorder."""

    try:
        result = subprocess.run(
            [python_exec, "-c", "import playwright"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        return f"Recorder Python executable not found: {exc}"
    except Exception as exc:  # noqa: BLE001
        return f"Failed to validate recorder runtime ({python_exec}): {exc}"

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip()
        details = stderr or stdout or "Playwright import failed for an unknown reason."
        instructions = (
            "Ensure Playwright is installed for this interpreter by running:\n"
            f"{python_exec} -m pip install playwright\n"
            f"{python_exec} -m playwright install chromium"
        )
        return f"Recorder dependencies are missing: {details}\n\n{instructions}"

    return None


def _finalize_recorder_session() -> None:
    session_dir = st.session_state.get("record_session_dir")
    if not session_dir:
        return
    listing = _scan_session_directory(session_dir)
    st.session_state["record_session_listing"] = listing
    metadata = _load_recorder_metadata(session_dir)
    if metadata:
        st.session_state["record_metadata"] = metadata
        missing_parts = []
        options = metadata.get("options", {})
        artifacts = metadata.get("artifacts", {})
        if options.get("captureDom") and not listing.get("dom_files"):
            missing_parts.append("DOM snapshots")
        if options.get("captureScreenshots") and not listing.get("screenshot_files"):
            missing_parts.append("screenshots")
        if options.get("recordTrace") and not artifacts.get("trace"):
            missing_parts.append("trace.zip")
        if options.get("recordHar") and not artifacts.get("har"):
            missing_parts.append("network.har")
        if missing_parts:
            st.warning(
                "Recorder metadata loaded but some expected artefacts appear to be missing: "
                + ", ".join(missing_parts)
            )
    else:
        existing = listing.get("top_level", []) if listing else []
        st.warning(
            "Recorder stopped but metadata.json is not available. "
            "Observed session directory contents: "
            + (", ".join(existing) if existing else "<empty>")
        )

proc = st.session_state.get("record_proc")
if proc and proc.poll() is not None:
    st.session_state["record_proc"] = None
    _finalize_recorder_session()

if "rec_output_dir" not in st.session_state:
    st.session_state["rec_output_dir"] = "recordings"
if "rec_capture_dom" not in st.session_state:
    st.session_state["rec_capture_dom"] = False
if "rec_capture_screens" not in st.session_state:
    st.session_state["rec_capture_screens"] = False
if "rec_capture_trace" not in st.session_state:
    st.session_state["rec_capture_trace"] = True
if "rec_capture_har" not in st.session_state:
    st.session_state["rec_capture_har"] = False
if "rec_ignore_https" not in st.session_state:
    st.session_state["rec_ignore_https"] = False
if "rec_timeout" not in st.session_state:
    st.session_state["rec_timeout"] = 0

st.text_input("Recording Output Directory", key="rec_output_dir")
opt_cols = st.columns(4)
with opt_cols[0]:
    st.checkbox("Capture DOM Snapshots", key="rec_capture_dom")
with opt_cols[1]:
    st.checkbox("Capture Screenshots", key="rec_capture_screens")
with opt_cols[2]:
    st.checkbox("Capture Playwright Trace", key="rec_capture_trace", value=True)
with opt_cols[3]:
    st.checkbox("Capture HAR", key="rec_capture_har")

st.checkbox(
    "Ignore HTTPS Errors",
    key="rec_ignore_https",
    help="Bypass TLS certificate validation (needed for some internal test environments).",
)

timeout_col, _ = st.columns([1, 3])
with timeout_col:
    st.number_input("Auto-stop after (seconds)", min_value=0, max_value=3600, step=60, key="rec_timeout")

status_placeholder = st.empty()
if st.session_state.get("record_proc"):
    status_placeholder.info("Recorder is running. Complete your browser actions and stop when finished.")

col1, col2 = st.columns(2)
with col1:
    if st.button("Start Recording") and not st.session_state["record_proc"]:
        normalized_url, url_error = _normalize_record_url(record_url)
        if url_error:
            st.error(url_error)
        else:
            session_name = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            output_root = Path(st.session_state["rec_output_dir"]).expanduser().resolve()
            output_root.mkdir(parents=True, exist_ok=True)
            session_dir = output_root / session_name
            python_exec = st.session_state.get("rec_python_executable") or sys.executable

            runtime_error = _validate_recorder_runtime(python_exec)
            if runtime_error:
                st.error(runtime_error)
                st.session_state["record_manual_log"] = runtime_error
            else:
                cmd: List[str] = [
                    python_exec,
                    "-m",
                    "app.run_playwright_recorder",
                    "--url",
                    normalized_url,
                    "--output-dir",
                    str(output_root),
                    "--session-name",
                    session_name,
                ]
                if not st.session_state["rec_capture_trace"]:
                    cmd.append("--no-trace")
                if not st.session_state["rec_capture_har"]:
                    cmd.append("--no-har")
                if st.session_state["rec_capture_dom"]:
                    cmd.append("--capture-dom")
                if st.session_state["rec_capture_screens"]:
                    cmd.append("--capture-screenshots")
                if st.session_state["rec_ignore_https"]:
                    cmd.append("--ignore-https-errors")
                if st.session_state["rec_timeout"]:
                    cmd.extend(["--timeout", str(int(st.session_state["rec_timeout"]))])

                creationflags = 0
                if os.name == "nt" and hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
                    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
                try:
                    proc = subprocess.Popen(cmd, creationflags=creationflags)
                    st.session_state["record_proc"] = proc
                    st.session_state["record_session_dir"] = str(session_dir)
                    st.session_state["record_metadata"] = None
                    st.session_state["record_manual_out_path"] = None
                    st.session_state["record_manual_log"] = ""
                    st.success(
                        f"Recorder started. A browser window should open. Session artefacts will appear in `{session_dir}`."
                    )
                except FileNotFoundError as exc:
                    st.error(f"Failed to launch recorder: {exc}")
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Unexpected error launching recorder: {exc}")

with col2:
    if st.button("Stop Recording") and st.session_state["record_proc"]:
        proc = st.session_state["record_proc"]
        try:
            if os.name == "nt" and hasattr(signal, "CTRL_BREAK_EVENT"):
                proc.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                proc.send_signal(signal.SIGINT)
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        finally:
            st.session_state["record_proc"] = None
            time.sleep(2)
            _finalize_recorder_session()
        st.info("Recorder stopped. Review captured metadata below.")

session_dir = st.session_state.get("record_session_dir")
session_listing = st.session_state.get("record_session_listing")
metadata = st.session_state.get("record_metadata")
if session_dir and session_listing:
    listing_lines = [
        f"metadata.json: {'present' if 'metadata.json' in session_listing.get('top_level', []) else 'missing'}",
        f"DOM snapshots: {session_listing.get('dom_files', 0)} file(s)",
        f"Screenshots: {session_listing.get('screenshot_files', 0)} file(s)",
    ]
    st.markdown("###### Session Directory Snapshot")
    st.code("\n".join(listing_lines))

if session_dir and metadata:
    session_path = Path(session_dir)
    actions = metadata.get("actions", [])
    st.success(
        f"Session `{session_path.name}` captured {len(actions)} actions "
        f"(HAR={'yes' if metadata['options'].get('recordHar') else 'no'}, "
        f"Trace={'yes' if metadata['options'].get('recordTrace') else 'no'})."
    )

    preview_rows = []
    for action in actions:
        element = action.get("element") or {}
        preview_rows.append(
            {
                "Action ID": action.get("actionId"),
                "Action": action.get("action"),
                "Element": element.get("tagName"),
                "Role": element.get("role"),
                "Name / Label": element.get("ariaLabel") or element.get("name") or element.get("text"),
                "Stable Selector": element.get("stableSelector"),
                "Quadrant": (action.get("boundingBox") or {}).get("quadrant", ""),
            }
        )
    if preview_rows:
        st.dataframe(pd.DataFrame(preview_rows), use_container_width=True, hide_index=True)

    st.markdown("##### Recorder Artefacts")
    metadata_path = session_path / "metadata.json"
    if metadata_path.exists():
        with open(metadata_path, "rb") as fh:
            st.download_button(
                "Download metadata.json",
                data=fh.read(),
                file_name=f"{session_path.name}_metadata.json",
                mime="application/json",
                key="download_metadata_json",
            )
    artifacts = metadata.get("artifacts", {})
    for label, rel_path in artifacts.items():
        if not rel_path:
            continue
        file_path = session_path / rel_path
        if file_path.exists():
            with open(file_path, "rb") as fh:
                st.download_button(
                    f"Download {label}",
                    data=fh.read(),
                    file_name=f"{session_path.name}_{Path(rel_path).name}",
                    key=f"download_{label}",
                )

    st.markdown("##### Generate Manual Test Cases from Recording")
    trace_rel = artifacts.get("trace")
    recording_source = session_path / trace_rel if trace_rel else None
    if recording_source and recording_source.exists():
        template_upload = st.file_uploader(
            "Upload Excel template", type=["xlsx"], key="rec_manual_template_uploader"
        )
        if st.button("Generate manual_from_recording.xlsx", key="btn_manual_from_recording"):
            if not template_upload:
                st.warning("Please upload an Excel template before generating manual test cases.")
            else:
                temp_dir = Path(tempfile.mkdtemp(prefix="manual_from_recording_"))
                template_path = temp_dir / template_upload.name
                template_path.write_bytes(template_upload.getvalue())
                out_path = temp_dir / f"manual_from_{session_path.name}.xlsx"
                cmd = [
                    sys.executable,
                    "manual_from_recording.py",
                    "--template",
                    str(template_path),
                    "--recording",
                    str(recording_source),
                    "--out",
                    str(out_path),
                ]
                dom_dir = session_path / "dom"
                if metadata["options"].get("captureDom") and dom_dir.exists():
                    cmd.extend(["--dom", str(dom_dir)])
                try:
                    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                    st.session_state["record_manual_out_path"] = str(out_path)
                    st.session_state["record_manual_log"] = (result.stdout or "") + (result.stderr or "")
                    st.success("Manual workbook generated successfully.")
                except subprocess.CalledProcessError as exc:
                    st.session_state["record_manual_log"] = (exc.stdout or "") + (exc.stderr or "")
                    st.error(f"manual_from_recording.py failed (exit {exc.returncode}). See logs below.")
        if st.session_state.get("record_manual_log"):
            st.code(st.session_state["record_manual_log"], language="bash")
        manual_out_path = st.session_state.get("record_manual_out_path")
        if manual_out_path and Path(manual_out_path).exists():
            with open(manual_out_path, "rb") as fh:
                st.download_button(
                    "Download manual test cases workbook",
                    data=fh.read(),
                    file_name=Path(manual_out_path).name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="download_manual_workbook",
                )
    else:
        st.info(
            "Trace artefact not found. Ensure trace capture is enabled or rerun the recorder with the default settings."
        )

# Paste TS code
st.markdown("### Paste Playwright TS Codegen Output")
ts_code = st.text_area("Paste code here...", height=300, key="ts_code_input")

if st.button("📥 Convert, Ingest & Generate Locators", key="btn_convert_ingest") and ts_code.strip():
    try:
        # 1️⃣ Parse TS Code → Steps
        steps = parse_playwright_code(ts_code)

        # 2️⃣ Save recorder flow JSON locally
        artifact = {"flow_name": flow_name, "source": "playwright", "steps": steps}
        json_path = os.path.join(JSON_FLOW_DIR, f"{flow_name}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(artifact, f, indent=4)

        # 3️⃣ Generate TypeScript locator file
        locator_file = os.path.join(LOCATOR_DIR, f"{flow_name}.ts")
        with open(locator_file, "w", encoding="utf-8") as f:
            f.write("export const Locators = {\n")
            for i, step in enumerate(steps):
                if "selector" in step:
                    locator_name = f"step{i+1}_{step['action']}".replace("-", "_")
                    cands = generate_xpath_candidates(step["selector"])  # list[str]
                    union_xpath = to_union_xpath(cands)
                    xpath_value = ("xpath=(" + union_xpath + ")").replace('"', '\\"')
                    f.write(f'  {locator_name}: "{xpath_value}",\n')
            f.write("};\n")

        table_rows, sidecar = enrich_recorder_flow(flow_name, steps)
        enriched_paths = persist_enriched_artifacts(flow_name, table_rows, sidecar)

        st.success(
            f"✅ Flow '{flow_name}' stored locally. Generated locators and enriched scenario artifacts (cache key: {enriched_paths['cache_key']})."
        )
        st.code(open(locator_file).read(), language="typescript")
        st.json(artifact)

        scenario_df = pd.DataFrame(
            table_rows,
            columns=["sl", "Action", "Navigation Steps", "Key Data Element Examples", "Expected Results"],
        )
        st.dataframe(scenario_df, hide_index=True)

        with open(enriched_paths["csv_path"], "rb") as f:
            st.download_button(
                label="📥 Download Scenario CSV",
                data=f.read(),
                file_name=f"{enriched_paths['cache_key']}.csv",
                mime="text/csv",
                key="download_scenario_csv",
            )

        if enriched_paths.get("xlsx_path"):
            with open(enriched_paths["xlsx_path"], "rb") as f:
                st.download_button(
                    label="📥 Download Scenario XLSX",
                    data=f.read(),
                    file_name=f"{enriched_paths['cache_key']}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="download_scenario_xlsx",
                )

        with open(enriched_paths["json_path"], "rb") as f:
            st.download_button(
                label="📥 Download Sidecar JSON",
                data=f.read(),
                file_name=f"{enriched_paths['cache_key']}.json",
                mime="application/json",
                key="download_scenario_json",
            )

        low_stability_targets = [
            idx + 1
            for idx, step_payload in enumerate(sidecar)
            if any(target.get("stability_score", 0) < 0.6 for target in step_payload.get("targets", []))
        ]
        summary_message = f"Scenario contains {enriched_paths['step_count']} rows."
        if low_stability_targets:
            summary_message += f" Low-stability selectors flagged at steps: {', '.join(map(str, low_stability_targets))}."
        st.info(summary_message)

    except Exception as e:
        st.error(f"❌ Failed to process recording: {e}")

# -------------------------- Test Case Generator Panel --------------------------
st.markdown("---")
st.subheader("Generate Test Cases from Jira / Keywords / Stories")
jira_input = st.text_area("Paste Jira story, description, or keywords", key="jira_input_area")
template_file = st.file_uploader(
    "Upload Template File (JSON / Excel / Text / Doc)",
    type=["json","xlsx","xls","txt","doc","docx"],
    key="template_file_uploader"
)

if st.button("Generate & Download Test Cases", key="btn_generate_tc") and jira_input.strip():
    try:
        tcg = TestCaseGenerator(db)
        results = tcg.generate_test_cases(jira_input.strip())
        if template_file:
            ext = os.path.splitext(template_file.name)[1].lower()
            if ext in [".xlsx", ".xls"]:
                template_df = load_excel_template(template_file)
                df = map_llm_to_template(results, template_df)
            else:
                df = pd.DataFrame(results)
        else:
            df = pd.DataFrame(results)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            df.to_excel(writer, index=False, sheet_name="TestCases")
        output.seek(0)
        st.download_button(
            label="📥 Download Test Cases as Excel",
            data=output,
            file_name="test_cases.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="btn_download_tc"
        )
    except Exception as e:
        st.error(f"Failed to generate test cases: {e}")

# -------------------------- Test Script Generator Panel --------------------------
# st.title("AI-Powered Test Script Generator")
# test_case_id = st.text_input("Enter Test Case ID", key="test_case_id_input")

# if st.button("Generate & Run", key="btn_generate_run"):
#     orch = TestScriptOrchestrator()
#     script, success, logs = orch.generate_and_run(test_case_id)

#     st.subheader("Generated Test Script")
#     st.code(script, language="typescript")

#     st.subheader("Execution Result")
#     if success:
#         st.success("✅ Passed – Script ingested into Vector DB")
#     else:
#         st.error("❌ Failed – Script NOT ingested")
#     st.text(logs)

# -------------------------- Repo Scaffold Ingestion --------------------------
def ingest_parsed_scaffold(parsed_json):
    """Ingest TS repo scaffold into Vector DB."""
    for module in parsed_json.get("modules", []):
        doc_id = module.get("id") or module.get("name")
        content = json.dumps(module, indent=2)
        metadata = {
            "type": "repo_scaffold",
            "module": module.get("name"),
        }
        db.add_document(source="repo_scaffold", doc_id=doc_id, content=content, metadata=metadata)

st.subheader("Pull Git Repo & Ingest Scaffold")

repo_url = st.text_input(
    "Git Repo URL",
    "https://github.com/keerthika-janardhanan/oracle_erp.git",
    key="repo_url_input2"
)
branch = st.text_input("Branch", "main", key="branch_input2")

def pull_and_ingest_repo(repo_url, branch):
    tmp_dir = tempfile.mkdtemp(prefix="repo_clone_")
    try:
        subprocess.run(["git", "clone", "--branch", branch, repo_url, tmp_dir], check=True)
        git_dir = os.path.join(tmp_dir, ".git")
        if os.path.exists(git_dir):
            shutil.rmtree(git_dir, ignore_errors=True)
        output_file = os.path.join(os.getcwd(), "parsed_repo_scaffold.json")
        subprocess.run(["node", "app/ts_parser.js", tmp_dir, output_file], check=True)
        with open(output_file, "r", encoding="utf-8") as f:
            parsed_json = json.load(f)
        ingest_parsed_scaffold(parsed_json)
        return parsed_json
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

if st.button("📥 Pull & Ingest Repo", key="btn_pull_ingest_repo"):
    if not repo_url.strip():
        st.warning("Please provide a valid repo URL")
    else:
        try:
            with st.spinner("Cloning repo and parsing with TS-Morph..."):
                parsed_json = pull_and_ingest_repo(repo_url, branch)
            st.success(f"✅ Repo scaffold ingested successfully: {len(parsed_json.get('modules', []))} modules")
        except subprocess.CalledProcessError as e:
            st.error(f"Git/Parser command failed: {e}")
        except Exception as ex:
            st.error(f"Unexpected error: {ex}")

st.title("Test Artifact Recorder & Ingest")

# ========================== Agentic AI Test Script Generator ==========================
st.header("Agentic AI Test Script Generator - Conversational Mode")

# Initialize conversation
if "conversation" not in st.session_state:
    st.session_state.conversation = []

# ------------------- User Input -------------------
user_input = st.text_input("Ask or type scenario / feedback:", key="chat_input")
uploaded_file = st.file_uploader(
    "Optional: Upload scenario/template file (JSON/Excel/Doc)", 
    type=["json","xlsx","xls","txt","doc","docx"],
    key="chat_file_uploader"
)

def flatten_file_keywords(uploaded_file):
    """Extract keywords from uploaded file"""
    keywords = []
    if uploaded_file:
        fname = uploaded_file.name
        ext = fname.split(".")[-1].lower()
        if ext in ["xlsx", "xls"]:
            df = load_excel_template(uploaded_file, dtype=str)
            keywords = df.fillna("").astype(str).to_numpy().flatten().tolist()
        elif ext == "json":
            data = json.load(uploaded_file)
            if isinstance(data, dict):
                keywords = list(data.values())
            elif isinstance(data, list):
                keywords = data
        else:
            # txt/doc/docx fallback
            content = uploaded_file.getvalue().decode(errors="ignore")
            keywords = content.splitlines()
    return keywords

def stream_ai_response(content: str, lang="typescript"):
    placeholder = st.empty()
    chunk_size = 50
    for i in range(0, len(content), chunk_size):
        chunk = content[:i+chunk_size]
        if lang:
            placeholder.code(chunk, language=lang)
        else:
            placeholder.markdown(chunk)
        time.sleep(0.02)
    return placeholder

def detect_intent(msg: str):
    msg_lower = msg.lower()
    if any(
        k in msg_lower
        for k in [
            "generate script",
            "create test script",
            "test script",
            "script preview",
            "automation script",
            "playwright script",
            "new script",
            "build script",
        ]
    ):
        return "agentic_script"
    if any(k in msg_lower for k in ["generate draft", "draft", "flow", "scenario"]):
        return "draft"
    if any(k in msg_lower for k in ["apply feedback", "modify", "change"]):
        return "feedback"
    if any(k in msg_lower for k in ["preview script", "show script", "script"]):
        return "agentic_script"
    return "unknown"

def search_existing_script(keywords):
    """Check existing framework / Vector DB for full actionable script"""
    artifacts = db.query(keywords, top_k=5)
    docs_list = artifacts.get("documents", []) if isinstance(artifacts, dict) else artifacts
    for doc in docs_list:
        content = doc.get("content", "") if isinstance(doc, dict) else str(doc)
        if keywords in content or keywords.replace(" ", "") in content:
            return content
    return None


def normalize_remote_repo_input(repo_input: str) -> Tuple[str, Optional[str]]:
    cleaned = repo_input.replace("\\", "/").strip()
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


def resolve_framework_repo(repo_input: str, branch: str) -> Tuple[Path, str]:
    repo_input = (repo_input or "").strip()
    if not repo_input:
        raise ValueError("Framework repo path is empty.")

    desired_branch = branch.strip() if branch else ""

    if any(repo_input.startswith(prefix) for prefix in ("http://", "https://", "git@")) or "github.com" in repo_input:
        clone_url, branch_in_url = normalize_remote_repo_input(repo_input)
        branch_to_use = branch_in_url or desired_branch
        slug_source = clone_url + (f"#{branch_to_use}" if branch_to_use else "")
        slug = hashlib.sha1(slug_source.encode("utf-8")).hexdigest()[:12]
        target = (FRAMEWORK_CLONE_BASE / slug).resolve()

        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "clone", clone_url, str(target)], check=True)

        subprocess.run(["git", "-C", str(target), "fetch", "origin"], check=True)
        if branch_to_use:
            subprocess.run(["git", "-C", str(target), "checkout", branch_to_use], check=True)
            subprocess.run(["git", "-C", str(target), "pull", "origin", branch_to_use], check=True)
        else:
            current_branch = subprocess.check_output(
                ["git", "-C", str(target), "rev-parse", "--abbrev-ref", "HEAD"],
                text=True,
            ).strip()
            branch_to_use = current_branch

        return target, branch_to_use

    path = Path(repo_input).expanduser()
    if not path.is_absolute():
        path = Path(os.getcwd()) / path
    path = path.resolve()
    if not path.exists():
        raise FileNotFoundError(f"Framework repo not found: {path}")
    if not desired_branch and (path / ".git").exists():
        try:
            desired_branch = subprocess.check_output(
                ["git", "-C", str(path), "rev-parse", "--abbrev-ref", "HEAD"],
                text=True,
            ).strip()
        except subprocess.CalledProcessError:
            desired_branch = "main"

    return path, desired_branch or "main"


def handle_agentic_message(message: str, intent: str) -> List[Dict[str, str]]:
    state = st.session_state.agentic_state
    repo_path = st.session_state.framework_repo_path.strip()

    if not repo_path:
        return [
            {
                "role": "assistant",
                "content": "Please set the Framework Repo Path in the sidebar before requesting script generation.",
                "type": "text",
            }
        ]

    try:
        resolved_path, active_branch = resolve_framework_repo(repo_path, st.session_state.framework_branch)
    except (FileNotFoundError, ValueError, subprocess.CalledProcessError) as exc:
        return [{"role": "assistant", "content": f"{exc}", "type": "text"}]

    st.session_state.framework_branch = active_branch
    st.session_state.resolved_framework_path = str(resolved_path)

    framework = FrameworkProfile.from_root(resolved_path)

    agent = agentic_engine
    responses: List[Dict[str, str]] = []

    if not state["active"] or state.get("status") in {"idle", "complete"} or intent == "agentic_script" and state.get("status") == "idle":
        st.session_state.agentic_state = initialise_agentic_state()
        state = st.session_state.agentic_state
        state["active"] = True
        state["scenario"] = message
        state["status"] = "preview-awaiting"
        state["feedback"] = []
        context = agent.gather_context(message)
        state["context"] = context
        preview = agent.generate_preview(message, framework, context)
        state["preview"] = preview
        responses.append({"role": "assistant", "content": preview, "type": "preview"})
        if not context.get("flow_available"):
            responses.append(
                {
                    "role": "assistant",
                    "content": "Recorder flow not found. Preview steps are derived from Jira/documentation/repository context.",
                    "type": "text",
                }
            )
        responses.append(
            {
                "role": "assistant",
                "content": "Review the preview steps. Reply with feedback to refine them or say 'confirm' to generate the full script.",
                "type": "text",
            }
        )
        return responses

    status = state.get("status")

    if status == "preview-awaiting":
        if interpret_confirmation(message):
            existing_assets = agent.find_existing_framework_assets(state["scenario"], framework)
            if existing_assets:
                state["status"] = "complete"
                state["active"] = False
                state["existing_files"] = [
                    str(asset["path"].relative_to(framework.root)) for asset in existing_assets
                ]
                files_list = []
                for asset in existing_assets:
                    rel = asset["path"].relative_to(framework.root)
                    files_list.append(str(rel))
                    try:
                        content = asset["path"].read_text(encoding="utf-8")
                    except UnicodeDecodeError:
                        content = "(Binary or non-UTF-8 content omitted)"
                    responses.append(
                        {
                            "role": "assistant",
                            "content": f"// {rel}\n{content}",
                            "type": "script",
                        }
                    )
                summary = "Existing framework files located:\n" + "\n".join(f"- {path}" for path in files_list)
                responses.append({"role": "assistant", "content": summary, "type": "text"})
                return responses
            try:
                payload = agent.generate_script_payload(state["scenario"], framework, state["preview"])
            except Exception as exc:  # noqa: BLE001
                return [
                    {
                        "role": "assistant",
                        "content": f"Failed to generate script: {exc}",
                        "type": "text",
                    }
                ]

            state["payload"] = payload
            state["status"] = "script-ready"
            state["written_files"] = []

            for section, files in payload.items():
                for file_obj in files:
                    display = f"// {file_obj['path']}\n{file_obj['content']}"
                    responses.append({"role": "assistant", "content": display, "type": "script"})

            responses.append(
                {
                    "role": "assistant",
                    "content": "Script generated. Reply 'push' to write the files and push to Git, or provide feedback to regenerate.",
                    "type": "text",
                }
            )
            return responses

        if interpret_push(message):
            return [
                {
                    "role": "assistant",
                    "content": "Preview must be confirmed before pushing. Please confirm the steps first.",
                    "type": "text",
                }
            ]

        state.setdefault("feedback", []).append(message)
        refined = agent.refine_preview(state["scenario"], framework, state["preview"], message)
        state["preview"] = refined
        responses.append({"role": "assistant", "content": refined, "type": "preview"})
        responses.append(
            {
                "role": "assistant",
                "content": "Preview updated. Reply 'confirm' when ready or continue sharing feedback.",
                "type": "text",
            }
        )
        return responses

    if status == "script-ready":
        if interpret_push(message):
            payload = state.get("payload")
            if not payload:
                return [{"role": "assistant", "content": "No script payload available to push.", "type": "text"}]

            if not state.get("written_files"):
                try:
                    written = agent.persist_payload(framework, payload)
                except Exception as exc:  # noqa: BLE001
                    return [{"role": "assistant", "content": f"Failed to persist files: {exc}", "type": "text"}]
                state["written_files"] = [str(p.relative_to(framework.root)) for p in written]

            success = agent.push_changes(
                framework,
                branch=st.session_state.framework_branch,
                commit_msg=st.session_state.framework_commit_message,
            )
            if success:
                state["status"] = "complete"
                state["active"] = False
                files_list = "\n".join(f"- {path}" for path in state["written_files"])
                responses.append(
                    {
                        "role": "assistant",
                        "content": f"Changes pushed successfully. Files:\n{files_list}",
                        "type": "text",
                    }
                )
            else:
                responses.append(
                    {
                        "role": "assistant",
                        "content": "Git push failed. Please check repository permissions and try again.",
                        "type": "text",
                    }
                )
            return responses

        if interpret_feedback(message):
            state.setdefault("feedback", []).append(message)
            refined = agent.refine_preview(state["scenario"], framework, state["preview"], message)
            state["preview"] = refined
            state["status"] = "preview-awaiting"
            state["payload"] = {}
            state["written_files"] = []
            responses.append({"role": "assistant", "content": refined, "type": "preview"})
            responses.append(
                {
                    "role": "assistant",
                    "content": "Script discarded. Review the updated preview and confirm when ready.",
                    "type": "text",
                }
            )
            return responses

        responses.append(
            {
                "role": "assistant",
                "content": "Script is ready. Reply 'push' to persist or provide feedback to adjust the flow.",
                "type": "text",
            }
        )
        return responses

    responses.append(
        {
            "role": "assistant",
            "content": "Agentic session complete. Start a new request for another script.",
            "type": "text",
        }
    )
    return responses

# ------------------- Process User Input -------------------
if st.button("Send") and user_input.strip():
    file_keywords = flatten_file_keywords(uploaded_file)
    combined_keywords = " ".join([user_input] + file_keywords).strip()

    st.session_state.conversation.append({"role": "user", "content": user_input})

    state = st.session_state.agentic_state
    intent = detect_intent(user_input)

    if state.get("active") or intent == "agentic_script":
        replies = handle_agentic_message(combined_keywords or user_input, intent)
    else:
        replies = handle_agentic_message(combined_keywords or user_input, "agentic_script")

    for reply in replies:
        st.session_state.conversation.append(reply)

# ------------------- Display Conversation -------------------
for msg in st.session_state.conversation:
    if msg["role"] == "user":
        st.markdown(f"**You:** {msg['content']}")
    else:
        msg_type = msg.get("type")
        if msg_type == "script":
            st.markdown("**AI (Script):**")
            st.code(msg["content"], language="typescript")
        elif msg_type in {"preview", "draft"}:
            st.markdown(f"**AI (Preview):**\n{msg['content']}")
        else:
            st.markdown(f"**AI:** {msg['content']}")
