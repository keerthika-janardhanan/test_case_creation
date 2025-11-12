# Backend extraction slice - recorder ingestion and test case generation

## Delivered job & queue infrastructure
- `app/job_store.py` persists job records; Celery is configured in `app/celery_app.py` and orchestrated via `app/tasks.py`.
- Recorder launch now shells out to the real Playwright recorder (`python -m app.run_playwright_recorder_v2`) with options propagated from the API payload. Job results capture stdout/stderr and the session directory, and live updates are published over the recorder event broker.
- `GET /api/jobs/{id}` exposes job state for UI polling.

## Expanded recorder & ingestion APIs
- `POST /api/recorder/sessions` queues a recorder launch, executing the full Playwright recorder workflow and returning `{jobId, sessionId}` when queued.
- `POST /api/recorder/sessions/{id}/stop` currently emits a warning event explaining that queue-driven stop is not yet supported.
- `GET /api/recorder/{sessionId}/artifacts/{path}` streams recorded artefacts from `RECORDER_OUTPUT_DIR`.
- Existing finalisation and event-stream endpoints remain available for post-processing.
- `POST /api/ingest/jira`, `POST /api/ingest/website`, and `POST /api/ingest/documents` mirror the Streamlit admin flows, enqueueing background jobs that surface progress via job polling and recorder events.
- Vector clean-up is exposed via `DELETE /api/vector/docs/{docId}` and `DELETE /api/vector/docs?source=...`.

## Frontend parity updates
- Recorder page now supports queuing launch/stop jobs, job lookup, and the existing finalise/event stream workflow against the real Celery-backed endpoints.
- The admin ingestion console (Jira, website, document upload, and vector maintenance) has been rebuilt in React; submissions hit the new `/api/ingest/*` routes and surface job IDs for follow-up.
- API clients expose helpers for new endpoints and shared job polling utilities.
- Streamlit admin controls can be feature-flagged via `ENABLE_STREAMLIT_ADMIN` to ease dual-mode migration.

## Testing & build
- Added `tests/test_job_store.py`, `tests/test_tasks.py`, and expanded job/endpoint checks in `tests/test_api_endpoints.py`.
- Frontend smoke coverage is provided via Vitest (`src/pages/__tests__`).
- React build (`npm run build`) and targeted pytest suite validate the queue/endpoint additions.

## Next steps
1. Wire Celery workers to actual recorder execution & ingestion workloads (hook run_playwright_recorder_v2).
2. Expand React parity across remaining Streamlit panels and incorporate streamed job progress UI.
3. Prepare infrastructure-as-code for FastAPI+Celery deployment (redis, storage) before dual-run migration.
