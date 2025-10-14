from __future__ import annotations
import argparse
import time
from pathlib import Path
from typing import Optional
import sys
from playwright.sync_api import sync_playwright

PAGE_INJECT_SCRIPT = """
(() => {
  const deliver = (name, payload) => { const fn = window && window[name]; if (typeof fn === 'function') { fn(payload); return true; } return false; };
  const sendCtx = (trigger) => { const payload = { pageUrl: location.href, title: document.title, timestamp: Date.now(), trigger }; deliver('pyCtx', payload); };
  document.addEventListener('DOMContentLoaded', () => sendCtx('domcontentloaded'));
  window.addEventListener('load', () => sendCtx('load'));
  sendCtx('init');
})();
"""

def main() -> int:
    parser = argparse.ArgumentParser(description="Minimal Playwright navigator for diagnostics.")
    parser.add_argument("--url", required=True)
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument("--ignore-https-errors", action="store_true")
    args = parser.parse_args()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context(ignore_https_errors=args.ignore_https_errors)
        ctx.add_init_script(PAGE_INJECT_SCRIPT)
        page = ctx.new_page()
        page.on('console', lambda msg: sys.stderr.write(f"[mini][console] {msg.type}: {msg.text}\n"))
        page.on('pageerror', lambda e: sys.stderr.write(f"[mini][pageerror] {e}\n"))
        try:
            page.goto(args.url, wait_until='domcontentloaded', timeout=30000)
            try:
                page.wait_for_load_state('load', timeout=15000)
            except Exception:
                pass
        except Exception as e:
            sys.stderr.write(f"[mini] goto failed: {e}\n")
        start = time.time()
        print(f"[mini] Opened {page.url}; waiting {args.timeout}s or Ctrl+C...")
        try:
            while time.time() - start < args.timeout:
                time.sleep(0.2)
        except KeyboardInterrupt:
            pass
        browser.close()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
