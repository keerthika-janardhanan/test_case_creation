# Copilot instructions for this repo

Purpose: AI-assisted creation of test assets for enterprise web apps (Oracle Fusion focus). It records rich Playwright metadata, ingests artifacts into a Chroma vector DB, generates manual test cases and Playwright scripts via Azure OpenAI, and can push scripts into existing automation frameworks.

## Architecture
- Recording (Python + Playwright): `app/run_playwright_recorder.py` launches a browser and writes `recordings/<session>/metadata.json` plus optional `dom/*.html`, `screenshots/*.png`, `network.har`, `trace.zip`.
- Ingestion + Vector DB: `app/ingest.py`, `app/ingest_utils.py`, `app/vector_db.py` add artifacts (Jira, website crawl, recorder flows, repo scaffolds) to Chroma with stable ids and flattened metadata.
- Test case generation: `app/test_case_generator.py` pulls relevant context from the vector DB and prompts Azure OpenAI to produce structured manual test cases; includes template mappers to Excel.
- Agentic script generation: `app/orchestrator.py`, `app/llm_client.py`, `app/framework_adapter.py`, and `app/streamlit_app.py` gather context, call the LLM, attempt self-healing of selectors, and can persist into framework repos.
- Utilities: locators (`app/locator_generator.py`), TS code parsing (`app/parse_playwright.py`), browser helpers (`app/browser_utils.py`), metadata + hashing (`app/metadata_utils.py`, `app/hashstore.py`).

## Core workflows
- Recorder (Windows PowerShell example):
  - Start: `python -m app.run_playwright_recorder --url "https://..." --output-dir recordings --session-name demo --capture-dom`
  - Stop via Ctrl+C/Ctrl+Break; finalize writes `metadata.json` summarizing `actions`, `pageContextEvents`, and `artifacts`.
- Vector DB CLI (persists under `./vector_store`):
  - Query: `python -m app.vector_db query "Create Supplier" --top-k 5`
  - List: `python -m app.vector_db list --limit 50`
- Streamlit UI: `python -m streamlit run app/streamlit_app.py` to control the recorder, ingest sources, generate manual cases (Excel), and run the agentic script flow.
- Trial-run a generated Playwright script: `app/executor.py::run_trial()` writes a temp `*.spec.ts` then runs `npx playwright test`.

## Conventions that matter
- Vector entries: call `VectorDBClient.add_document(source, doc_id, content, metadata)`; ids are stored as `<source>-<doc_id>`. Use `hashstore.is_changed()` for idempotence.
- Flatten metadata (lists/dicts → JSON strings) prior to add; see `flatten_metadata()` in `app/ingest.py` and usage in Streamlit.
- Saved recorder flows: JSON at `app/saved_flows/*.json` shaped as `{ flow_name, source, steps }`. Consumers expect this shape.
- Sanitization: redact sensitive values (`app/metadata_utils.sanitize_events`, recorder masks `valueMasked`) and record `sensitive_fields_masked` in metadata.
- Browser selection: always normalize via `browser_utils.normalize_browser_name()`; it auto-corrects close typos.
- LLM: use Azure OpenAI via `langchain_openai.AzureChatOpenAI`; env vars required: `AZURE_OPENAI_KEY`, `AZURE_OPENAI_ENDPOINT`, `OPENAI_API_VERSION`, `AZURE_OPENAI_DEPLOYMENT`.
- Framework prompt: when calling `llm_client.ask_llm_for_script(...)`, pass a prompt from `framework_adapter.get_framework_prompt('playwright'|'selenium-java'|'cypress')`.

## Integration points
- Jira, website docs, UI crawl: routed through `app/ingest.py` and stored with `artifact_type`/`type` metadata (e.g., `repo_scaffold`, `ui_crawl`, `test_case`).
- TS repo parsing: `app/ts_parser.js` (ts-morph) writes `parsed_repo_scaffold.json` which is then ingested via Streamlit.
- Recorder enrichment: `recorder_enricher` and `template_utils` produce CSV/XLSX columns (`SL, Action, Navigation Steps, Key Data Element Examples, Expected Results`) that mappers expect.

## Tips and pitfalls
- Ensure Playwright for Python is installed for the chosen interpreter and browsers are installed (`playwright install chromium`); Node is required for `npx playwright` and ts-morph.
- Recorder’s signal handling finalizes metadata; if missing, check process termination or permissions on the output dir.
- Some legacy tests reference non-existent modules (e.g., `app.recorder.FlowRecorder`); maintain tests around existing modules (`browser_utils`, `metadata_utils`, `vector_db`).
- Prefer resilient XPath unions via `locator_generator.to_union_xpath()`; avoid brittle ids.

## Example: inject recorder steps into manual case
- `TestCaseGenerator._load_saved_flows()` loads `app/saved_flows/*.json` and `_inject_flow_details()` ensures the first positive case mirrors recorder `step_details` and `steps`.

Unclear or missing? Tell me which part (recorder output shape, ingestion metadata, LLM env, or framework push flow) you want expanded and I’ll refine this file.