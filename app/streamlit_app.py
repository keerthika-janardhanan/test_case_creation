# streamlit_app.py
import os
import io
import json
import subprocess
import pandas as pd
import streamlit as st
from hashstore import init_db
from vector_db import VectorDBClient
from test_case_generator import TestCaseGenerator
from ingest_utils import ingest_artifact
from ingest import ingest_jira, ingest_web_site, ingest_ui_crawl, ingest_document
from parse_playwright import parse_playwright_code
from test_case_generator import map_llm_to_template

# -------------------------- Constants --------------------------
JSON_FLOW_DIR = os.path.join(os.getcwd(), "app", "saved_flows")
os.makedirs(JSON_FLOW_DIR, exist_ok=True)
os.makedirs("uploads", exist_ok=True)

# -------------------------- Initialize DB & Vector --------------------------
init_db()
db = VectorDBClient()

# -------------------------- Page Config --------------------------
st.set_page_config(page_title="Test Artifact Recorder & Ingest", layout="wide")

# -------------------------- Authentication (demo) --------------------------
if "role" not in st.session_state:
    st.session_state["role"] = "user"
st.sidebar.header("Login (demo)")
st.session_state["role"] = st.sidebar.selectbox("Select role", ["user", "admin"], index=0)

st.title("Test Artifact Recorder & Ingest")

# -------------------------- Helper: Flatten Metadata --------------------------
def flatten_metadata(meta: dict) -> dict:
    """Flatten metadata and remove None values for Chroma compatibility."""
    import json
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
    jql_input = st.text_input("Jira JQL", value="project=GEN_AI_PROJECT ORDER BY created DESC")
    if st.button("Fetch & Ingest Jira"):
        try:
            results = ingest_jira(jql_input)
            st.success(f"Jira stories ingested: {len(results)} issues ✅")
        except Exception as e:
            st.error(f"Jira ingestion failed: {e}")

    # ---------------- Website ----------------
    st.subheader("Website Ingestion")
    url = st.text_input("Website URL", value="https://docs.oracle.com/en/cloud/saas/index.html")
    max_depth = st.number_input("Max Depth", min_value=1, max_value=5, value=2)
    if st.button("Fetch & Ingest Website"):
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
        accept_multiple_files=True
    )

    if uploaded_files:
        if st.button("Ingest Uploaded Documents"):
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
    crawl_file = st.file_uploader("Upload crawl JSON", type=["json"])
    if st.button("Ingest UI Crawl"):
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
    delete_mode = st.radio("Choose delete mode", ["By ID", "By Source"])
    
    if delete_mode == "By ID":
        doc_id_input = st.text_input("Enter Document ID to delete")
        if st.button("🗑️ Delete Document by ID"):
            if doc_id_input.strip():
                try:
                    db.delete_document(doc_id_input.strip())
                    st.success(f"Document '{doc_id_input}' deleted successfully ✅")
                except Exception as e:
                    st.error(f"Failed to delete document: {e}")
            else:
                st.warning("Please enter a valid Document ID.")
    
    elif delete_mode == "By Source":
        source_input = st.text_input("Enter Source (e.g. 'jira', 'ui_flow')")
        if st.button("🗑️ Delete All Documents by Source"):
            if source_input.strip():
                try:
                    db.delete_by_source(source_input.strip())
                    st.success(f"All documents from source '{source_input}' deleted ✅")
                except Exception as e:
                    st.error(f"Failed to delete by source: {e}")
            else:
                st.warning("Please enter a valid source name.")

    # ---------------- Show Existing Docs ----------------
    if st.checkbox("📋 Show Existing Docs with Pagination"):
        try:
            all_docs = db.list_all(limit=1000) # fetch up to 10k docs
            if all_docs:
                page_size = st.number_input("Docs per page", min_value=5, max_value=100, value=20)
                total_pages = (len(all_docs) + page_size - 1) // page_size
                current_page = st.number_input("Page", min_value=1, max_value=total_pages, value=1)

                start_idx = (current_page - 1) * page_size
                end_idx = start_idx + page_size
                page_docs = all_docs[start_idx:end_idx]

                df = pd.DataFrame(page_docs)
                st.dataframe(df)  # scrollable

                st.write(f"Showing page {current_page} of {total_pages}")
            else:
                st.info("No documents found in Vector DB.")
        except Exception as e:
            st.error(f"Failed to fetch documents: {e}")

# -------------------------- Playwright Recorder Panel --------------------------
st.header("🎥 Playwright Recorder → Vector DB Ingestion")
flow_name = st.text_input("Flow Name", "playwright-recorded-flow")
record_url = st.text_input("URL to Record", "https://example.com")

if "record_proc" not in st.session_state:
    st.session_state["record_proc"] = None

col1, col2 = st.columns(2)
with col1:
    if st.button("▶ Start Recording") and not st.session_state["record_proc"]:
        st.session_state["record_proc"] = subprocess.Popen(f"npx playwright codegen {record_url}", shell=True)
        st.success("Recorder started, perform your flow in the browser.")
with col2:
    if st.button("⏹ Stop Recording") and st.session_state["record_proc"]:
        st.session_state["record_proc"].terminate()
        st.session_state["record_proc"].wait()
        st.session_state["record_proc"] = None
        st.info("Recorder stopped. Paste the TS output below.")

# ---------------- Paste & Ingest TS code ----------------
st.markdown("### Paste Playwright TS Codegen Output")
ts_code = st.text_area("Paste code here...", height=300)
if st.button("📥 Convert & Ingest") and ts_code.strip():
    try:
        steps = parse_playwright_code(ts_code)
        artifact = {"flow_name": flow_name, "source": "playwright", "steps": steps}
        json_path = os.path.join(JSON_FLOW_DIR, f"{flow_name}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(artifact, f, indent=4)
        metadata = {
            "artifact_type": "ui_flow",
            "source": "playwright-recorder",
            "flow_name": flow_name,
            "steps_count": len(steps)
        }
        metadata = flatten_metadata(metadata)
        doc_id = f"playwright_{abs(hash(flow_name))}"
        db.add_document(source="ui_flow", doc_id=doc_id, content=json.dumps(artifact), metadata=metadata)
        st.success(f"Flow '{flow_name}' ingested successfully ✅")
        st.json(artifact)
    except Exception as e:
        st.error(f"Failed to convert & ingest: {e}")

# -------------------------- Test Case Generator Panel --------------------------
st.markdown("---")
st.subheader("Generate Test Cases from Jira / Keywords / Stories")
jira_input = st.text_area("Paste Jira story, description, or keywords")
template_file = st.file_uploader("Upload Template File (JSON / Excel / Text / Doc)", type=["json","xlsx","xls","txt","doc","docx"])

if st.button("Generate & Download Test Cases") and jira_input.strip():
    try:
        tcg = TestCaseGenerator(db)
        results = tcg.generate_test_cases(jira_input.strip())
        if template_file:
            ext = os.path.splitext(template_file.name)[1].lower()
            if ext in [".xlsx", ".xls"]:
                template_df = pd.read_excel(template_file)
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
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except Exception as e:
        st.error(f"Failed to generate test cases: {e}")
