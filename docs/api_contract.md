# API Contract: Test Artifact Platform (FastAPI)

This document defines the initial REST/SSE contracts to migrate from Streamlit to a React + FastAPI architecture. All responses use application/json unless otherwise noted. Auth is JWT via `Authorization: Bearer <token>` on protected routes.

## Conventions
- Base URL: http://localhost:8000
- Errors: `{ "error": { "code": string, "message": string, "details"?: any } }`
- IDs and paths: All returned file paths are relative to the configured framework repo root unless explicitly absolute.
- Streaming: SSE endpoints use `text/event-stream` with events: `message`, `error`, `done`.

---

## POST /manual/table
Generate a manual table from refined/vector context.

Request
```
{
  "story": "Create Supplier",
  "dbQuery": "",
  "scope": "",
  "coverage": "full",            // "grouped" | "full"
  "includeUnlabeled": false,
  "includeLogin": false
}
```
Response
```
{ "markdown": "| sl | Action | ..." }
```

---

## POST /cases/generate
Generate structured manual test cases.

Request
```
{ "story": "Create Supplier", "llmOnly": false }
```
Response
```
{ "cases": [ { "type": "positive", "steps": ["..."], "expected": "..." } ] }
```

---

## POST /agentic/preview
Produce step preview for a scenario.

Request
```
{ "scenario": "Create volunteering team for project" }
```
Response
```
{ "preview": "1. Click | ...\n2. Fill | ..." }
```

SSE alternative: `POST /agentic/preview/stream` emits progress events while generating the preview.

Event frames (text/event-stream, JSON per data frame):
```
{ "phase": "start" }
{ "phase": "gather_context" }
{ "phase": "context_ready", "flow_available": true }
{ "phase": "preview", "preview": "1. Click | Button" }
{ "phase": "done" }
```

### POST /agentic/refine
Apply feedback to the preview.
```
{ "scenario": "...", "previousPreview": "...", "feedback": "remove steps 19 and 20" }
```
Response
```
{ "preview": "... (updated list) ..." }
```

### POST /agentic/payload
Generate files from accepted preview.
```
{ "scenario": "...", "acceptedPreview": "..." }
```
Response
```
{ "locators": [{"path":"locators/slug.ts","content":"..."}],
  "pages":    [{"path":"pages/SlugPage.ts","content":"..."}],
  "tests":    [{"path":"tests/slug.spec.ts","content":"..."}] }
```

SSE alternative: `POST /agentic/payload/stream` emits progress phases and a brief payload summary.

Event frames:
```
{ "phase": "start" }
{ "phase": "gather_context" }
{ "phase": "context_ready", "flow_available": true }
{ "phase": "payload", "summary": { "locators": 1, "pages": 1, "tests": 1 } }
{ "phase": "done" }
```

### POST /agentic/persist (protected)
Write generated files to disk.
```
{ "files": [{"path":"...","content":"..."}] }
```
Response
```
{ "written": ["pages/SlugPage.ts", "tests/slug.spec.ts"] }
```

### POST /agentic/push (protected)
Push committed changes to git.
```
{ "branch": "feature/agentic", "message": "Add generated Playwright test" }
```
Response
```
{ "success": true }
```

---

## POST /files/upload (protected)
multipart/form-data
- `file`: <binary>
- `target`: "uploads" | "framework-data"

Response
```
{ "path": "data/CreateSupplierData.xlsx" }
```

---

## POST /config/update_test_manager (protected)
Update or create an entry in `testmanager.xlsx`.
```
{ "scenario": "Create Supplier", "datasheet": "CreateSupplierData.xlsx", "referenceId": "CreateSupplier001", "idName": "CreateSupplierID" }
```
Response
```
{ "path": "testmanager.xlsx", "mode": "updated" | "created" | "unchanged", "description": "Create Supplier" }
```

---

## POST /recorder/start (protected)
Start the recorder session.
```
{ "url": "https://...", "sessionName": "20250101_120000", "options": { "captureDom": true, "captureScreenshots": false, "recordHar": true, "recordTrace": true } }
```
Response
```
{ "sessionId": "20250101_120000", "status": "started" }
```

### POST /recorder/stop (protected)
```
{ "sessionId": "20250101_120000" }
```
Response
```
{ "status": "stopped", "artifacts": { "trace": ".../trace.zip", "har": ".../network.har" } }
```

### GET /recorder/status/{sessionId}
Response
```
{ "status": "running" | "stopped", "artifacts": { ... }, "files": ["dom/*.html", "screenshots/*.png"] }
```

---

## POST /trial/run (protected)
Run a spec and return summary.
```
{ "specPath": "tests/slug.spec.ts", "headed": false }
```
Response
```
{ "status": "PASS" | "FAIL", "logs": "..." }
```
SSE: `/trial/stream?spec=tests/slug.spec.ts`

---

## POST /vector/query
Query the vector DB.
```
{ "query": "Create Supplier", "topK": 5, "where": {"type":"recorder_refined"} }
```
Response
```
{ "results": [{"id":"...","content":"...","metadata":{...}}] }
```

---

## Error model
```
{ "error": { "code": "BadRequest", "message": "...", "details": {"field":"coverage"} } }
```

---

## Auth and CORS
- JWT on protected routes (uploads, recorder, persist, push, trial).
- CORS allowOrigins: `http://localhost:5173` during dev.

---

## Mapping to current modules
- Manual/cases → `app/test_case_generator.py` (generate_manual_table, generate_test_cases)
- Agentic → `app/agentic_script_agent.py` (generate_preview, refine_preview, generate_script_payload, persist_payload, push_changes)
- Recorder → `app/run_playwright_recorder_v2.py`, `app/recorder_auto_ingest.py`
- Vector → `app/vector_db.py`
- Trial → `app/executor.py::run_trial`
- Config (datasheet) → `app/streamlit_app.py::update_test_manager_entry` (to be lifted into a utility)

---

## Risks & mitigations (API layer)
- Long-running calls → Use background tasks and SSE for progress; timeouts with resume.
- File path traversal → Normalize and enforce repo root commonpath; whitelist directories.
- Version drift with Streamlit → Keep Streamlit side-by-side; parity tests before cutover.
- LLM/network variability → Keep deterministic fallbacks; cap timeouts; return actionable error messages.
