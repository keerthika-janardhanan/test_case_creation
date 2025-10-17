# Copilot instructions for this repo

Goal: Help AI agents generate high‑quality manual test cases and Playwright scripts for enterprise web apps (Oracle Fusion focus) by using the recorder output, a Chroma vector DB, and Azure OpenAI. The Streamlit app orchestrates most flows end‑to‑end.

## Big picture
- Recorder (Python + Playwright): `app/run_playwright_recorder_v2.py` (preferred) or `app/run_playwright_recorder.py` writes `recordings/<session>/metadata.json`, plus `dom/*.html`, `screenshots/*.png`, `network.har`, `trace.zip`.
- Ingestion + Vector DB: `app/ingest.py`, `app/ingest_utils.py`, `app/vector_db.py` load Jira/docs/UI crawl/recorder flows/repo scaffolds into Chroma with stable ids and flattened metadata.
- Manual test cases: `app/test_case_generator.py` queries the vector DB and crafts structured cases; `map_llm_to_template()` maps to Excel columns.
- Agentic scripts: `app/agentic_script_agent.py`, `app/llm_client.py`, `app/framework_adapter.py`, and `app/streamlit_app.py` build previews, generate TS assets, self‑heal selectors, and push to external framework repos.
- Utilities: locators (`app/locator_generator.py`), TS parsing (`app/parse_playwright.py`), browser utils (`app/browser_utils.py`), metadata + hashing (`app/metadata_utils.py`, `app/hashstore.py`).

## Core workflows (PowerShell examples)
- Recorder: `python -m app.run_playwright_recorder_v2 --url "https://..." --output-dir recordings --session-name demo --capture-dom` (Ctrl+C to finalize `metadata.json`).
- Streamlit UI: `streamlit run app/streamlit_app.py` to record, ingest, generate manual cases (Excel), and run the agentic flow.
- Vector DB CLI (data under `./vector_store` or `VECTOR_DB_PATH`):
  - Query: `python -m app.vector_db query "Create Supplier" --top-k 5`
  - List: `python -m app.vector_db list --limit 50`
- Trial a generated script: `app/executor.py::run_trial()` writes a temp `*.spec.ts` and runs `npx playwright test`.
- Tests: run the VS Code task “Run tests with Python” (pytest -q) or `python -m pytest -q`.

## Conventions and data shapes
- Vector IDs: `VectorDBClient.add_document(source, doc_id, content, metadata)` stores ids as `<source>-<doc_id>`; use `hashstore.is_changed()` to avoid dup writes.
- Metadata: flatten lists/dicts to JSON strings before ingest; see `flatten_metadata()` in `app/ingest.py`.
- Saved recorder flows: JSON at `app/saved_flows/*.json` with shape `{ flow_name, source, steps }`.
- Sanitization: redact sensitive inputs via `metadata_utils.sanitize_events` (recorder emits `valueMasked`); record `sensitive_fields_masked` in metadata.
- Browser selection: normalize via `browser_utils.normalize_browser_name()`.
- LLM config: use Azure via `langchain_openai.AzureChatOpenAI` with env vars `AZURE_OPENAI_KEY`, `AZURE_OPENAI_ENDPOINT`, `OPENAI_API_VERSION`, `AZURE_OPENAI_DEPLOYMENT`.
- Selector strategy: prefer Playwright `getByRole/getByLabel/getByText`; only fall back to resilient XPath unions from `locator_generator.to_union_xpath()`.

## Agentic script flow (Streamlit)
1) Describe scenario → preview steps (Markdown) via `AgenticScriptAgent.generate_preview`.
2) Confirm preview (“confirm/yes”) → LLM produces JSON of files (`locators/pages/tests`) aligned to `FrameworkProfile` discovery of pages/locators/tests dirs in the target repo.
3) “push” writes files to the detected repo structure and optionally pushes via `git_utils.push_to_git`.
4) Self‑heal failures: `llm_client.ask_llm_to_self_heal` uses execution logs + UI crawl; updates `locator_cache.json`.

## Integrations and ingestion
- Jira/docs/UI crawl: handled in `app/ingest.py` → store with `artifact_type`/`type` (e.g., `repo_scaffold`, `ui_crawl`, `test_case`).
- TS repo scaffold: `app/ts_parser.js` (ts‑morph) writes `parsed_repo_scaffold.json`; ingest with `app/ingest_scaffold.py`.
- Recorder enrichment: `recorder_enricher` + `template_utils` produce Excel‑friendly columns: SL, Action, Navigation Steps, Key Data Element Examples, Expected Results.

## Gotchas
- Chroma client versions differ: `query_where/get_where` handle fallbacks if filters aren’t supported. Prefer `query_where` for filtered search.
- Ensure Playwright for Python and browsers are installed; Node is required for `npx playwright` and ts‑morph.
- Some legacy references (e.g., `app.recorder.FlowRecorder`) don’t exist; focus tests on `browser_utils`, `metadata_utils`, `vector_db`, etc.

Questions or gaps? If you need deeper detail, say which area to expand: recorder output shape, ingestion metadata, LLM env, agentic push flow, or vector DB filters.