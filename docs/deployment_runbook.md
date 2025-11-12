# Deployment Runbook – React + FastAPI + Celery

## Target Architecture
- **API layer**: FastAPI served via `uvicorn` or `gunicorn` behind your platform load balancer.
- **Background workers**: Celery workers plus an optional beat scheduler for housekeeping jobs.
- **Broker / cache**: Redis cluster (or Azure Service Bus/SQS alternatives) providing the Celery broker and optional result backend.
- **Frontend**: React bundle built with Vite; serve statically via CDN/object storage (S3 + CloudFront, Azure Static Web Apps, etc.) or mount under FastAPI for small deployments.
- **Storage**: Shared filesystem or object storage for recorder artefacts (trace.zip, har, metadata). Configure via `RECORDER_OUTPUT_DIR` or move to S3/GCS with signed download URLs.

## Environment & Secrets
| Component | Variables | Notes |
|-----------|-----------|-------|
| FastAPI | `API_HOST`, `API_PORT`, `ENABLE_STREAMLIT_ADMIN` (toggle legacy panels) | host/port for local runs; feature flag to gate remaining Streamlit UI |
| Celery / Workers | `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `CELERY_TASK_ALWAYS_EAGER` (set to `0` in production) | broker/backends (e.g. `redis://user:pass@host:6379/0`) |
| Recorder | `RECORDER_OUTPUT_DIR`, `RECORDER_HEADLESS`, `PLAYWRIGHT_BROWSERS_PATH` | configure output root and recorder defaults; ensure worker image has Playwright browsers installed |
| Ingestion | API keys/credentials for Jira, web crawling proxies, cloud storage | manage via secret store (AWS Secrets Manager, Azure Key Vault, etc.) |
| Frontend | `VITE_API_BASE_URL`, OAuth client IDs, feature flags | embed via build-time env or runtime config |

Use your platform's secret manager for sensitive values; avoid committing `.env` files. Container orchestrations (ECS, AKS, Kubernetes) should inject secrets and mount storage volumes or buckets.

## Deployment Steps
1. **Build artifacts**
   - API: package FastAPI + Celery into container images (include Playwright dependencies).
   - Frontend: `npm run build` and publish the `dist/` bundle to CDN or the API static mount.
2. **Provision infrastructure**
   - Redis (or chosen broker), Postgres/SQLite hosted volume if persisting jobs externally.
   - Object storage for recorder artefacts if not using shared disk.
   - Monitoring/observability (APM, log aggregation, Celery flower).
3. **Deploy services**
   - Run FastAPI behind a process manager (gunicorn/uvicorn workers).
   - Run one or more Celery worker replicas plus optional beat for scheduled jobs.
   - Serve the React bundle at `/` with API proxied under `/api` (CORS configured if using separate domains).
4. **Configure dual mode**
   - Keep Streamlit app accessible for legacy users; set `ENABLE_STREAMLIT_ADMIN=0` to hide panels already ported to React.
   - Route beta traffic to the React SPA + FastAPI API; monitor error budgets, job success rates, and user feedback.
   - Instrument telemetry (GA/App Insights/Prometheus) to track feature usage in both UIs.
5. **Cutover & retirement**
   - Once parity is validated (all workflows available in React, Celery queues stable), redirect production traffic to the SPA.
   - Archive the Streamlit app/code paths and remove feature flags.
   - Update runbooks and on-call procedures to reflect the new architecture.

## CI/CD Considerations
- Add pipelines for:
  - Backend: lint + `pytest`, image build, container scan, deploy.
  - Frontend: lint + `npm run test -- --run`, bundle build, upload to storage/CDN.
- Optional Playwright smoke: orchestrate API + frontend in an ephemeral environment, run a headless flow (record ? ingest ? generate tests).
- Automate Celery worker readiness checks (ping task) during deployment health probes.

## Operational Checklist
- [ ] Redis/Celery metrics monitored (queue depth, retry counts).
- [ ] Recorder workers have Playwright browsers installed (`npx playwright install chromium`).
- [ ] Storage path has sufficient quota and lifecycle policies for artefacts.
- [ ] Observability dashboards cover API latency, job throughput, and frontend errors.
- [ ] Incident runbook updated to include job/job_id investigation via `/api/jobs/{id}` and event stream taps.
