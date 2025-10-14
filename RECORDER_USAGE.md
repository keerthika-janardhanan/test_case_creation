# Playwright Recorder Usage

This project ships with an instrumented Playwright recorder that persists rich metadata for every manual interaction. Follow the steps below to launch it locally and collect a session.

## 1. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows use `.venv\\Scripts\\activate`
pip install -r requirements.txt
```

## 2. Run the recorder

Invoke the v2 recorder module directly with the URL you want to explore:

```bash
python -m app.run_playwright_recorder_v2 --url https://example.com
```

Key optional flags:

- `--output-dir`: directory where session artifacts (metadata, trace, HAR, etc.) will be written. Defaults to `recordings/`.
- `--session-name`: folder name for the session; defaults to a timestamp if omitted.
- `--capture-dom`: persist DOM snapshots for each interaction.
- `--capture-screenshots`: capture per-action element screenshots.
- `--no-trace` / `--no-har`: disable Playwright trace or HAR capture if not needed.
- `--timeout`: auto-stop the session after the given number of seconds.
- `--ignore-https-errors`: skip TLS/SSL certificate errors (handy for internal/self-signed environments).
- `--user-agent`: spoof the reported browser user agent (defaults to a realistic desktop Chrome string).

Refer to `python -m app.run_playwright_recorder --help` for the full list of options.

## 3. Interact with the browser

A Playwright browser window opens with the provided URL. Perform your manual actions. Use **Ctrl+C** in the terminal to stop recording (or let the timeout elapse). The script prints the paths to the generated artifacts, including `metadata.json`, traces, and HAR files when enabled.

## 4. Inspect the output

Artifacts live under `<output-dir>/<session-name>/`. The `metadata.json` file contains every captured action along with contextual UI details used by downstream tooling. Navigation events are also recorded with full-page DOM and screenshot snapshots (P-### files) so you can review a session even if no interactive events fire. Per-action artifacts (A-### files) appear when you actually interact (click, type, submit, etc.).

## Alternative: Streamlit UI

You can also manage recordings via the Streamlit dashboard (uses the same v2 recorder under the hood):

```bash
streamlit run app/streamlit_app.py
```

The "Recorder" section mirrors the CLI flags and launches the same module with your selections.
