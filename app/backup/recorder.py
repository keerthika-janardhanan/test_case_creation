# recorder.py
from playwright.sync_api import sync_playwright
import json, time, uuid

session_id = f"workflow_{uuid.uuid4()}"
events = []

def log_event(event_type, detail=None, element=None, value=None, url=None):
    events.append({
        "timestamp": time.time(),
        "session_id": session_id,
        "event": event_type,
        "element": element,
        "value": value,
        "url": url or detail or ""
    })

def record():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        # Log navigations
        page.on("framenavigated", lambda frame: log_event("goto", url=frame.url))

        # Log requests
        page.on("request", lambda req: log_event("request", detail=req.url))

        # Example actions
        def patched_fill(selector, value, *args, **kwargs):
            log_event("input", element=selector, value=value, url=page.url)
            return original_fill(selector, value, *args, **kwargs)

        def patched_click(selector, *args, **kwargs):
            log_event("click", element=selector, url=page.url)
            return original_click(selector, *args, **kwargs)

        # Monkey patch Playwright fill/click
        original_fill = page.fill
        original_click = page.click
        page.fill = patched_fill
        page.click = patched_click

        # Start with homepage
        page.goto("https://example.com")

        input("Press Enter to stop recording...")

        # Save raw file
        with open(f"{session_id}_raw.json", "w") as f:
            json.dump(events, f, indent=2)

        context.close()
        browser.close()

if __name__ == "__main__":
    record()
