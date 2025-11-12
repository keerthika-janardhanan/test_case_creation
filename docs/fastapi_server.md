# FastAPI server (skeleton)

This backend runs alongside the Streamlit app and exposes API endpoints used by the planned React UI.

## Run locally (dev)

Windows PowerShell:

```powershell
$env:API_HOST="0.0.0.0"; $env:API_PORT="8000"; uvicorn app.api.main:app --host $env:API_HOST --port $env:API_PORT --reload
```

Open http://localhost:8000/healthz to verify.

## Notable endpoints (skeleton)
- /healthz
- /manual/table (501)
- /cases/generate (501)
- /agentic/* (501)
- /recorder/* (501)
- /trial/run (501)
- /trial/stream (SSE placeholder)
- /files/upload (protected; placeholder)
- /config/update_test_manager (protected; 501)
- /vector/query (501)

Existing service endpoints retained under /api/* (pre-existing Streamlit-integrated API).

## CORS and Auth
- CORS allows http://localhost:5173 by default (set ALLOW_ORIGINS to override, comma-separated).
- JWT hooks are placeholders in `app/api/auth.py`.

## Next steps
- Implement /manual/table and /cases/generate wiring.
- Fill agentic/recorder/trial/files/config/vector endpoints and streaming.
