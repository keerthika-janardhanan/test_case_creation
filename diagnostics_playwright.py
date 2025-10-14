from pathlib import Path
from playwright.sync_api import sync_playwright

URL = "https://ecqg-test.fa.us2.oraclecloud.com"
OUT_DIR = Path("recordings") / "metadata-dom" / "diagnostics"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Optional custom UA similar to recorder default
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

with sync_playwright() as pw:
    print("[diag] Starting Playwright")
    browser = pw.chromium.launch(headless=False, devtools=True)  # devtools=True opens the inspector for debugging
    context = browser.new_context(ignore_https_errors=False, user_agent=DEFAULT_USER_AGENT)
    page = context.new_page()

    def _on_console(msg):
        try:
            print(f"[console] {msg.type}: {msg.text}")
        except Exception:
            print(f"[console] (unparsable message) {msg}")

    def _on_pageerror(exc):
        print(f"[pageerror] {exc}")

    def _on_requestfailed(req):
        try:
            failure = getattr(req, "failure", lambda: "")()
        except Exception:
            failure = ""
        print(f"[requestfailed] {req.url} -> {failure}")

    page.on("console", _on_console)
    page.on("pageerror", _on_pageerror)
    page.on("requestfailed", _on_requestfailed)

    try:
        print(f"[diag] Navigating to: {URL}")
        response = page.goto(URL, wait_until="domcontentloaded", timeout=45000)
        status = response.status if response else None
        print(f"[diag] Navigation response status: {status}")
    except Exception as e:
        print(f"[diag] page.goto() raised: {e}")
        status = None

    # allow a few seconds for scripts to run / extra console messages
    page.wait_for_timeout(5000)

    try:
        html = page.content()
        html_path = OUT_DIR / "page.html"
        html_path.write_text(html, encoding="utf-8")
        print(f"[diag] Saved page HTML ({len(html)} bytes) to: {html_path}")
    except Exception as e:
        print(f"[diag] Failed to save page HTML: {e}")

    try:
        shot_path = OUT_DIR / "diagnostic.png"
        page.screenshot(path=str(shot_path), full_page=True)
        print(f"[diag] Saved screenshot to: {shot_path}")
    except Exception as e:
        print(f"[diag] Screenshot failed: {e}")

    # keep the browser open for manual inspection for a short time
    print("[diag] Pausing for 10s while you can inspect the UI... (close browser to continue)")
    page.wait_for_timeout(10000)

    browser.close()
    print("[diag] Done.")