# recorder_sync.py
from playwright.sync_api import sync_playwright
import time

_stop_flag = False

def stop_recording():
    global _stop_flag
    _stop_flag = True

def record_flow_sync(flow_name, url, user, headless=True):
    """
    Synchronous recorder function using Playwright.
    Returns recorded steps as list.
    """
    global _stop_flag
    _stop_flag = False
    recorded_steps = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()

        # Inject recorder JS (replace with your actual RECORDER_JS)
        from recorder import RECORDER_JS
        page.add_init_script(RECORDER_JS)

        # Collect console events
        def handle_console(msg):
            text = msg.text
            if text.startswith("__PY_RECORDER__:"):
                import json
                try:
                    payload = json.loads(text.replace("__PY_RECORDER__:", ""))
                    recorded_steps.append(payload)
                except: pass

        page.on("console", handle_console)
        page.goto(url)
        print(f"[Recorder] Recording started for {flow_name} at {url}")

        # Simple recording loop until stop
        while not _stop_flag:
            time.sleep(0.5)

        browser.close()
        print(f"[Recorder] Recording stopped for {flow_name}")

    return recorded_steps
