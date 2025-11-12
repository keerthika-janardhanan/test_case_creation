"""Instrumented Playwright recorder: robust navigation + rich diagnostics.

Artifacts per session:
  recordings/<session>/
    - metadata.json
    - dom/*.html              (with --capture-dom)
    - screenshots/*.png       (with --capture-screenshots)
    - network.har             (unless --no-har)
    - trace.zip               (unless --no-trace)

Usage (PowerShell):
  python -m app.run_playwright_recorder --url "https://example.com" --capture-dom --timeout 20
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from types import FrameType
from typing import Any, Dict, List, Optional, Tuple

from playwright.sync_api import (
  Browser,
  BrowserContext,
  ConsoleMessage,
  Frame,
  Page,
  Playwright,
  Request,
  Response,
  sync_playwright,
)

from app.browser_utils import SUPPORTED_BROWSERS, normalize_browser_name


# ----------------------------- Defaults -----------------------------
DEFAULT_USER_AGENT = (
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
  "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


# ----------------------------- Helpers ------------------------------
def _iso_now() -> str:
  return datetime.now(timezone.utc).isoformat()


def _mask(value: Optional[str]) -> Optional[str]:
  if value is None:
    return None
  s = str(value)
  low = s.lower()
  if any(tok in low for tok in ("password", "secret", "token", "otp")):
    return "********"
  if "@" in s and " " not in s:
    return "<email>"
  return s if len(s) <= 64 else f"{s[:8]}...{s[-4:]}"


def _signal_name(signum: int) -> str:
  try:
    return signal.Signals(signum).name
  except Exception:  # noqa: BLE001
    return str(signum)


def _install_signal_handlers(stop_event: threading.Event) -> List[Tuple[int, Any]]:
  installed: List[Tuple[int, Any]] = []

  def _handler(received_signum: int, frame: Optional[FrameType]) -> None:  # noqa: ARG001
    if not stop_event.is_set():
      sys.stderr.write(
        f"[recorder] Signal {_signal_name(received_signum)} received. Stopping...\n"
      )
      stop_event.set()

  for signame in ("SIGINT", "SIGTERM", "SIGBREAK"):
    signum = getattr(signal, signame, None)
    if signum is None:
      continue
    try:
      prev = signal.getsignal(signum)
      signal.signal(signum, _handler)
      installed.append((signum, prev))
    except (AttributeError, ValueError, OSError):
      continue
  return installed


def _restore_signal_handlers(handlers: List[Tuple[int, Any]]) -> None:
  for signum, handler in handlers:
    try:
      signal.signal(signum, handler)
    except (AttributeError, ValueError, OSError):
      pass


# ----------------------- Page-side instrumentation ------------------
PAGE_INJECT_SCRIPT = """
(() => {
  try {
    if (window.__pyRecorderInstalled) {
      return;
    }
    window.__pyRecorderInstalled = true;
  } catch (_) {}

  const deliver = (name, payload) => {
    const fn = window && window[name];
    if (typeof fn === "function") {
      fn(payload);
      return true;
    }
    return false;
  };

  const captureQueue = [];
  const contextQueue = [];

  const flushQueues = () => {
    while (captureQueue.length && deliver("pythonRecorderCapture", captureQueue[0])) {
      captureQueue.shift();
    }
    while (contextQueue.length && deliver("pythonRecorderPageContext", contextQueue[0])) {
      contextQueue.shift();
    }
  };
  setInterval(flushQueues, 200);

  const normaliseTarget = (raw) => {
    if (!raw) return null;
    if (raw.nodeType === Node.TEXT_NODE) {
      return raw.parentElement;
    }
    if (raw.nodeType === Node.ELEMENT_NODE) {
      return raw;
    }
    return null;
  };

  const safeText = (value, limit = 150) => {
    if (!value) return "";
    return String(value).trim().slice(0, limit);
  };

  const buildXPath = (el) => {
    if (!el || el.nodeType !== 1) return "";
    const segments = [];
    let node = el;
    while (node && node.nodeType === 1) {
      const parent = node.parentNode;
      if (!parent) {
        segments.unshift(node.nodeName.toLowerCase());
        break;
      }
      const siblings = Array.from(parent.children).filter((child) => child.nodeName === node.nodeName);
      const index = siblings.indexOf(node) + 1;
      segments.unshift(`${node.nodeName.toLowerCase()}[${index}]`);
      node = parent.nodeType === 1 ? parent : null;
    }
    return "/" + segments.join("/");
  };

  const buildCssPath = (el) => {
    if (!el || el.nodeType !== 1) return "";
    const parts = [];
    let node = el;
    while (node && node.nodeType === 1) {
      const id = node.id && node.id.trim();
      if (id) {
        parts.unshift(`${node.nodeName.toLowerCase()}#${id}`);
        break;
      }
      const parent = node.parentNode;
      if (!parent) break;
      const index = Array.from(parent.children).indexOf(node) + 1;
      parts.unshift(`${node.nodeName.toLowerCase()}:nth-child(${index})`);
      node = parent;
    }
    return parts.join(" > ");
  };

  const snapshot = (raw) => {
    const el = normaliseTarget(raw);
    if (!el) return null;
    let rect = null;
    try {
      rect = el.getBoundingClientRect();
    } catch (_) {
      rect = null;
    }
    return {
      tag: (el.tagName || "").toLowerCase(),
      id: safeText(el.id, 80),
      className: safeText(el.className, 80),
      text: safeText(el.textContent, 120),
      xpath: buildXPath(el),
      cssPath: buildCssPath(el),
      rect: rect
        ? { x: rect.x, y: rect.y, width: rect.width, height: rect.height }
        : null,
    };
  };

  const queueCapture = (action, target, extra = {}) => {
    const payload = {
      action,
      pageUrl: location.href,
      pageTitle: document.title,
      timestamp: Date.now(),
      element: snapshot(target),
      extra,
    };
    if (!deliver("pythonRecorderCapture", payload)) {
      captureQueue.push(payload);
    }
  };

  const queueContext = (trigger) => {
    const payload = {
      pageUrl: location.href,
      title: document.title,
      timestamp: Date.now(),
      trigger,
    };
    if (!deliver("pythonRecorderPageContext", payload)) {
      contextQueue.push(payload);
    }
  };

  const primaryTarget = (event) => {
    try {
      if (event && typeof event.composedPath === "function") {
        const path = event.composedPath();
        if (path && path.length) {
          return path[0];
        }
      }
    } catch (_) {}
    return event ? event.target : null;
  };

  document.addEventListener(
    "click",
    (event) => {
      const target = primaryTarget(event);
      queueCapture("click", target, { button: event.button });
    },
    true
  );

  document.addEventListener(
    "change",
    (event) => {
      queueCapture("change", event.target, { value: event.target && event.target.value });
    },
    true
  );

  document.addEventListener(
    "input",
    (event) => {
      queueCapture("input", event.target, { value: event.target && event.target.value });
    },
    true
  );

  document.addEventListener(
    "keydown",
    (event) => {
      if (["Enter", "Escape", "Tab"].includes(event.key)) {
        queueCapture("press", event.target, { key: event.key });
      }
    },
    true
  );

document.addEventListener("DOMContentLoaded", () => queueContext("domcontentloaded"));
window.addEventListener("load", () => queueContext("load"));
queueContext("init");
})();
"""

# ------------------------------ Core flow ---------------------------
def _ensure_playwright() -> Playwright:
  try:
    return sync_playwright().start()
  except Exception as exc:  # noqa: BLE001
    raise RuntimeError("Failed to start Playwright. Ensure browsers are installed: `python -m playwright install chromium`." ) from exc


def _build_context(
  playwright: Playwright,
  browser_name: str,
  headless: bool,
  slow_mo: Optional[int],
  har_path: Optional[Path],
  ignore_https_errors: bool,
  user_agent: Optional[str],
) -> BrowserContext:
  normalized = normalize_browser_name(browser_name, SUPPORTED_BROWSERS)
  browser_factory = getattr(playwright, normalized)
  browser: Browser = browser_factory.launch(headless=headless, slow_mo=slow_mo)
  ctx_kwargs: Dict[str, Any] = {"ignore_https_errors": ignore_https_errors}
  if har_path:
    ctx_kwargs.update(record_har_path=str(har_path), record_har_mode="minimal")
  if user_agent:
    ctx_kwargs["user_agent"] = user_agent
  return browser.new_context(**ctx_kwargs)


def _await_user(timeout: Optional[int], stop_event: threading.Event) -> None:
  start = time.time()
  try:
    while not stop_event.is_set():
      time.sleep(0.2)
      if timeout and time.time() - start >= timeout:
        print(f"[recorder] Auto-stopping after {timeout} seconds.")
        stop_event.set()
        break
  except KeyboardInterrupt:
    print("\n[recorder] Stopping (Ctrl+C detected).")
    stop_event.set()


def main() -> None:
  parser = argparse.ArgumentParser(description="Open a browser and record rich UI metadata.")
  parser.add_argument("--url", required=True, help="Initial URL to open.")
  parser.add_argument("--output-dir", default="recordings", help="Base directory for artifacts.")
  parser.add_argument("--session-name", default=None, help="Session folder name (default: timestamp).")
  parser.add_argument("--browser", default="chromium", help=f"Browser engine ({', '.join(SUPPORTED_BROWSERS)}).")
  parser.add_argument("--headless", action="store_true", help="Run browser in headless mode.")
  parser.add_argument("--slow-mo", type=int, default=None, help="Slow down actions by N ms.")
  parser.add_argument("--timeout", type=int, default=None, help="Auto-stop after N seconds.")
  parser.add_argument("--no-trace", action="store_true", help="Disable Playwright trace capture.")
  parser.add_argument("--no-har", action="store_true", help="Disable HAR/network capture.")
  parser.add_argument("--capture-dom", action="store_true", help="Persist DOM snapshot for each action.")
  parser.add_argument("--capture-screenshots", action="store_true", help="Capture screenshots for actions.")
  parser.add_argument("--ignore-https-errors", action="store_true", help="Skip TLS certificate validation.")
  parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT, help="Override browser User-Agent.")

  args = parser.parse_args()

  # Normalize browser name
  try:
    args.browser = normalize_browser_name(args.browser, SUPPORTED_BROWSERS)
  except ValueError as exc:
    parser.error(str(exc))

  # Session dirs
  output_root = Path(args.output_dir).resolve()
  output_root.mkdir(parents=True, exist_ok=True)
  session_name = args.session_name or datetime.now().strftime("%Y%m%d_%H%M%S")
  session_dir = output_root / session_name
  session_dir.mkdir(parents=True, exist_ok=True)

  stop_event = threading.Event()
  handlers = _install_signal_handlers(stop_event)

  har_path = None if args.no_har else session_dir / "network.har"
  trace_path = None if args.no_trace else session_dir / "trace.zip"

  print(f"[recorder] Session directory: {session_dir}")
  print(f"[recorder] Launching browser ({args.browser}) at {args.url}")
  if args.timeout:
    print(f"[recorder] Will auto-stop after {args.timeout} seconds or Ctrl+C.")
  else:
    print("[recorder] Press Ctrl+C to stop recording.")

  playwright = _ensure_playwright()
  context: Optional[BrowserContext] = None
  browser: Optional[Browser] = None
  trace_started = False

  # Prepare session
  session = RecorderSession(
    session_dir=session_dir,
    capture_dom=args.capture_dom,
    capture_screenshots=args.capture_screenshots,
    options={
      "browser": args.browser,
      "headless": args.headless,
      "slowMo": args.slow_mo,
      "captureDom": args.capture_dom,
      "captureScreenshots": args.capture_screenshots,
      "recordHar": not args.no_har,
      "recordTrace": not args.no_trace,
      "url": args.url,
      "ignoreHttpsErrors": args.ignore_https_errors,
      "userAgent": args.user_agent,
    },
  )

  try:
    context = _build_context(
      playwright=playwright,
      browser_name=args.browser,
      headless=args.headless,
      slow_mo=args.slow_mo,
      har_path=har_path,
      ignore_https_errors=args.ignore_https_errors,
      user_agent=args.user_agent,
    )
    browser = context.browser

    # Bindings BEFORE any navigation
    context.expose_binding("pythonRecorderCapture", lambda source, payload: _on_capture(session, source, payload, args))
    context.expose_binding("pythonRecorderPageContext", lambda source, payload: _on_page_context(session, source, payload))
    context.add_init_script(PAGE_INJECT_SCRIPT)

    # Diagnostics
    context.on("requestfailed", lambda req: sys.stderr.write(f"[recorder][requestfailed] {req.url} -> {getattr(req, 'failure', lambda: '')()}\n"))

    page = context.new_page()
    page.on("console", _on_console)
    page.on("pageerror", _on_page_error)

    # Trace
    if trace_path is not None:
      try:
        context.tracing.start(screenshots=True, snapshots=True, sources=True)
        trace_started = True
      except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"[recorder] Failed to start tracing: {exc}\n")

    # Navigate
    page.goto(args.url, wait_until="domcontentloaded")

    _await_user(args.timeout, stop_event)

    # Stop trace if active
    if trace_started and trace_path is not None:
      try:
        context.tracing.stop(path=str(trace_path))
      except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"[recorder] Failed to stop tracing: {exc}\n")

    context.close()
    browser.close()
    playwright.stop()

    meta_path = session.finalize(har_path=har_path, trace_path=trace_path)
    print(f"[recorder] Recorded {len(session.actions)} actions.")
    print(f"[recorder] Metadata saved to {meta_path}")
    if har_path and har_path.exists():
      print(f"[recorder] HAR saved to {har_path}")
    if trace_path and trace_path.exists():
      print(f"[recorder] Trace saved to {trace_path}")
    if args.capture_dom:
      print(f"[recorder] DOM snapshots: {len(list((session.dom_dir).glob('*.html')))} file(s)")
    if args.capture_screenshots:
      print(f"[recorder] Screenshots: {len(list((session.screenshot_dir).glob('*.png')))} file(s)")

  except KeyboardInterrupt:
    stop_event.set()
    sys.stderr.write("[recorder] Interrupt received. Cleaning up...\n")
  except Exception as exc:  # noqa: BLE001
    stop_event.set()
    sys.stderr.write(f"[recorder] Unexpected error: {exc}\n")
    raise
  finally:
    try:
      if context and not context.is_closed():
        context.close()
    except Exception:
      pass
    try:
      if browser and browser.is_connected():
        browser.close()
    except Exception:
      pass
    try:
      playwright.stop()
    except Exception:
      pass
    _restore_signal_handlers(handlers)


# ------------------------------- Callbacks --------------------------
def _on_console(msg: ConsoleMessage) -> None:
  try:
    sys.stderr.write(f"[recorder][console] {msg.type}: {msg.text}\n")
  except Exception:
    pass


def _on_page_error(exc: Exception) -> None:
  try:
    sys.stderr.write(f"[recorder][pageerror] {exc}\n")
  except Exception:
    pass


def _on_page_context(session: RecorderSession, source: Any, payload: Dict[str, Any]) -> None:
  session.add_page_event(payload)


def _on_capture(session: RecorderSession, source: Any, payload: Dict[str, Any], args: argparse.Namespace) -> None:
  """Process an element capture event from the page (called via expose_binding)."""
  record = dict(payload or {})

  # Optional DOM snapshot
  if args.capture_dom:
    try:
      frame = getattr(source, "frame", None)
      html = None
      scope = "page"
      if frame is not None:
        try:
          html = frame.content()
          scope = "frame"
        except Exception:
          html = None
      if html is None:
        page = getattr(source, "page", None)
        if page is not None:
          try:
            html = page.content()
            scope = "page"
          except Exception:
            html = None
      if html:
        idx = len(session.actions) + 1
        dom_path = session.dom_dir / f"A-{idx:03}.html"
        dom_path.write_text(html, encoding="utf-8")
        record["domSnapshotPath"] = str(dom_path.relative_to(session.session_dir))
        record["domSnapshotScope"] = scope
    except Exception as exc:  # noqa: BLE001
      record["domSnapshotError"] = str(exc)

  # Optional screenshot
  if args.capture_screenshots:
    try:
      page = getattr(source, "page", None)
      if page and not page.is_closed():
        idx = len(session.actions) + 1
        shot_path = session.screenshot_dir / f"A-{idx:03}.png"
        clip = None
        element_rect = ((record.get("element") or {}).get("rect") or None)
        if element_rect and all(k in element_rect for k in ("x", "y", "width", "height")):
          clip = {
            "x": max(0, float(element_rect.get("x", 0))),
            "y": max(0, float(element_rect.get("y", 0))),
            "width": max(1, float(element_rect.get("width", 1))),
            "height": max(1, float(element_rect.get("height", 1))),
          }
        try:
          if clip:
            page.screenshot(path=str(shot_path), clip=clip)
          else:
            page.screenshot(path=str(shot_path), full_page=True)
          record["screenshotPath"] = str(shot_path.relative_to(session.session_dir))
        except Exception:
          # Fallback to full-page on any clip error
          page.screenshot(path=str(shot_path), full_page=True)
          record["screenshotPath"] = str(shot_path.relative_to(session.session_dir))
    except Exception as exc:  # noqa: BLE001
      record["screenshotError"] = str(exc)

  session.add_action(record)


 
def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mask_sensitive(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = str(value)
    lowered = text.lower()
    sensitive_tokens = ("password", "secret", "token", "passcode", "otp")
    if any(token in lowered for token in sensitive_tokens):
        return "********"
    if "@" in text and " " not in text:
        return "<email>"
    if len(text) > 64:
        return f"{text[:8]}...{text[-4:]}"
    return text


class RecorderSession:
    def __init__(
        self,
        session_dir: Path,
        capture_dom: bool,
        capture_screenshots: bool,
        stop_event: threading.Event,
        options: Dict[str, Any],
    ) -> None:
        self.session_dir = session_dir
        self.capture_dom = capture_dom
        self.capture_screenshots = capture_screenshots
        self.stop_event = stop_event
        self.options = dict(options)
        self.actions: List[Dict[str, Any]] = []
        self.page_events: List[Dict[str, Any]] = []
        self.action_counter = 0
        self.started_at = _iso_now()
        self.screenshot_dir = self.session_dir / "screenshots"
        self.dom_dir = self.session_dir / "dom"
        self._page_lock = threading.Lock()
        self._pages: Dict[int, Page] = {}
        self._last_page_id: Optional[int] = None
        self._metadata_lock = threading.Lock()
        self._ended_at: Optional[str] = None
        self._artifacts: Dict[str, Optional[str]] = {"har": None, "trace": None}
        self.metadata_path = self.session_dir / "metadata.json"
        self._last_navigation_url: Optional[str] = None
        if self.capture_screenshots:
            self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        if self.capture_dom:
            self.dom_dir.mkdir(parents=True, exist_ok=True)
        self._persist_metadata()

    def _build_summary(self) -> Dict[str, Any]:
        summary: Dict[str, Any] = {
            "session": {
                "id": self.session_dir.name,
                "startedAt": self.started_at,
            },
            "options": self.options,
            "pageContextEvents": self.page_events,
            "actions": self.actions,
            "artifacts": self._artifacts,
        }
        if self._ended_at:
            summary["session"]["endedAt"] = self._ended_at
        return summary

    def _persist_metadata(self) -> None:
        with self._metadata_lock:
            summary = self._build_summary()
            try:
                self.metadata_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
            except Exception as exc:  # noqa: BLE001
                sys.stderr.write(f"[recorder] Failed to persist metadata snapshot: {exc}\n")

    @staticmethod
    def _page_key(page: Page) -> int:
        return id(page)

    def register_page(self, page: Optional[Page]) -> None:
        if page is None:
            return
        key = self._page_key(page)
        with self._page_lock:
            self._pages[key] = page
            self._last_page_id = key

    def unregister_page(self, page: Optional[Page]) -> None:
        if page is None:
            return
        key = self._page_key(page)
        with self._page_lock:
            self._pages.pop(key, None)
            if self._last_page_id == key:
                self._last_page_id = next(iter(self._pages), None)

    def _resolve_page(self, source: Any) -> Optional[Page]:
        candidate = getattr(source, "page", None)
        if candidate:
            self.register_page(candidate)
            return candidate
        frame = getattr(source, "frame", None)
        if frame is not None:
            try:
                frame_page = frame.page  # type: ignore[attr-defined]
            except Exception:
                frame_page = None
            if frame_page:
                self.register_page(frame_page)
                return frame_page
        with self._page_lock:
            if self._last_page_id is not None:
                return self._pages.get(self._last_page_id)
        return None

    def handle_page_context(self, source: Any, payload: Dict[str, Any]) -> None:
        event = dict(payload or {})
        event["receivedAt"] = _iso_now()
        queued_at = event.get("queuedAt")
        if queued_at:
            try:
                queued_at_int = int(queued_at)
            except Exception:
                queued_at_int = None
            if queued_at_int:
                event["queuedAt"] = queued_at_int
        self.page_events.append(event)
        self._persist_metadata()

        page = self._resolve_page(source)
        frame = getattr(source, "frame", None)

        url = event.get("pageUrl")
        if url:
            needs_record = False
            if self._last_navigation_url is None:
                needs_record = True
            elif self._last_navigation_url != url:
                needs_record = True
            elif not self.actions:
                needs_record = True
            if needs_record:
                self._record_navigation(event, page, frame)
                self._last_navigation_url = url
        self._persist_metadata()

    def handle_capture(self, source: Any, payload: Dict[str, Any]) -> None:
        self.action_counter += 1
        action_id = f"A-{self.action_counter:03}"

        record: Dict[str, Any] = dict(payload or {})
        record["actionId"] = action_id
        record["receivedAt"] = _iso_now()

        element = record.get("element") or {}
        value = element.get("value")
        element["valueMasked"] = _mask_sensitive(value)

        extra = record.get("extra")
        if isinstance(extra, dict):
            for key in ("value", "text", "inputValue"):
                if key in extra:
                    extra[f"{key}Masked"] = _mask_sensitive(extra[key])

        record["element"] = element

        frame = getattr(source, "frame", None)
        if frame:
            try:
                record.setdefault("frameUrl", frame.url)
            except Exception:
                pass

        page = self._resolve_page(source)
        if page:
            record.setdefault("pageRef", str(self._page_key(page)))

        if self.stop_event.is_set():
            return

        if self.capture_screenshots and page and not page.is_closed():
            clip = record.get("boundingBox")
            screenshot_result = self._capture_screenshot(page, action_id, clip)
            if screenshot_result:
                screenshot_path, used_full_page = screenshot_result
                record["screenshotPath"] = screenshot_path
                if used_full_page:
                    record["screenshotFullPage"] = True

        if self.capture_dom and (page or frame) and not self.stop_event.is_set():
            dom_result = self._capture_dom(page, frame, action_id)
            if dom_result:
                dom_path = dom_result.get("path")
                if dom_path:
                    record["domSnapshotPath"] = dom_path
                scope = dom_result.get("scope")
                if scope:
                    record["domSnapshotScope"] = scope
                error = dom_result.get("error")
                if error:
                    record.setdefault("domSnapshotError", error)

        # Guarantee current page URL/title
        if page:
            try:
                record.setdefault("pageUrl", record.get("pageUrl") or page.url)
            except Exception:
                pass
            try:
                record.setdefault("pageTitle", record.get("pageTitle") or page.title())
            except Exception:
                pass
        elif frame:
            try:
                record.setdefault("pageUrl", record.get("pageUrl") or frame.url)
            except Exception:
                pass

        self.actions.append(record)
        # Helpful debug output
        sys.stderr.write(f"[recorder] captured {action_id} -> {record.get('action')}\n")
        self._persist_metadata()

    def _record_navigation(
        self,
        event: Dict[str, Any],
        page: Optional[Page],
        frame: Optional[Frame],
    ) -> None:
        self.action_counter += 1
        action_id = f"A-{self.action_counter:03}"
        record: Dict[str, Any] = {
            "actionId": action_id,
            "action": "navigate",
            "category": "navigation",
            "pageUrl": event.get("pageUrl"),
            "pageTitle": event.get("title"),
            "timestamp": event.get("timestamp"),
            "receivedAt": _iso_now(),
            "trigger": event.get("trigger"),
            "breadcrumbs": event.get("breadcrumbs", []),
            "viewport": event.get("viewport"),
        }
        queued_at = event.get("queuedAt")
        if queued_at:
            record["queuedAt"] = queued_at

        if frame:
            try:
                record.setdefault("frameUrl", frame.url)
            except Exception:
                pass

        if page:
            record.setdefault("pageRef", str(self._page_key(page)))

        if self.capture_screenshots and page and not page.is_closed():
            screenshot_result = self._capture_screenshot(page, action_id, None)
            if screenshot_result:
                screenshot_path, used_full_page = screenshot_result
                record["screenshotPath"] = screenshot_path
                if used_full_page:
                    record["screenshotFullPage"] = True

        if self.capture_dom and (page or frame) and not self.stop_event.is_set():
            dom_result = self._capture_dom(page, frame, action_id)
            if dom_result:
                dom_path = dom_result.get("path")
                if dom_path:
                    record["domSnapshotPath"] = dom_path
                scope = dom_result.get("scope")
                if scope:
                    record["domSnapshotScope"] = scope
                error = dom_result.get("error")
                if error:
                    record.setdefault("domSnapshotError", error)

        self.actions.append(record)
        sys.stderr.write(f"[recorder] captured {action_id} -> navigate\n")

    def _capture_screenshot(
        self, page: Page, action_id: str, clip: Optional[Dict[str, Any]]
    ) -> Optional[Tuple[str, bool]]:
        try:
            path = self.screenshot_dir / f"{action_id}.png"
            used_full_page = False
            if clip and all(clip.get(key) not in (None, 0) for key in ("width", "height")):
                clip_dict = {
                    "x": max(0, float(clip.get("x", 0))),
                    "y": max(0, float(clip.get("y", 0))),
                    "width": max(1, float(clip.get("width", 1))),
                    "height": max(1, float(clip.get("height", 1))),
                }
                try:
                    page.screenshot(path=str(path), clip=clip_dict)
                except Exception as clip_exc:  # noqa: BLE001
                    used_full_page = True
                    sys.stderr.write(
                        f"[recorder] Element clip failed for {action_id}, falling back to full-page screenshot: {clip_exc}\n"
                    )
                    page.screenshot(path=str(path), full_page=True)
            else:
                used_full_page = True
                page.screenshot(path=str(path), full_page=True)
            return str(path.relative_to(self.session_dir)), used_full_page
        except KeyboardInterrupt:
            self.stop_event.set()
            sys.stderr.write(f"[recorder] Screenshot interrupted for {action_id}.\n")
            return None
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(f"[recorder] Failed to capture screenshot for {action_id}: {exc}\n")
            return None

    def _capture_dom(
        self,
        page: Optional[Page],
        frame: Optional[Frame],
        action_id: str,
    ) -> Optional[Dict[str, str]]:
        html: Optional[str] = None
        scope = "page"
        errors: List[str] = []
        if frame is not None:
            try:
                html = frame.content()
                scope = "frame"
            except Exception as frame_exc:  # noqa: BLE001
                errors.append(f"frame:{frame_exc}")
        if html is None and page is not None:
            try:
                html = page.content()
                scope = "page"
            except Exception as page_exc:  # noqa: BLE001
                errors.append(f"page:{page_exc}")
        if html is None:
            if errors:
                sys.stderr.write(f"[recorder] Failed to obtain DOM for {action_id}: {'; '.join(errors)}\n")
                return {"error": "; ".join(errors)}
            return None
        try:
            path = self.dom_dir / f"{action_id}.html"
            path.write_text(html, encoding="utf-8")
            result: Dict[str, str] = {
                "path": str(path.relative_to(self.session_dir)),
                "scope": scope,
            }
            if errors:
                result["error"] = "; ".join(errors)
            return result
        except KeyboardInterrupt:
            self.stop_event.set()
            sys.stderr.write(f"[recorder] DOM capture interrupted for {action_id}.\n")
            return {"error": "interrupted"}
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(f"[recorder] Failed to capture DOM for {action_id}: {exc}\n")
            combined_error = "; ".join(errors + [str(exc)]) if errors else str(exc)
            return {"error": combined_error}

    def finalize(self, har_path: Optional[Path], trace_path: Optional[Path]) -> Path:
        self._ended_at = _iso_now()
        if har_path and har_path.exists():
            try:
                self._artifacts["har"] = str(har_path.relative_to(self.session_dir))
            except Exception:
                self._artifacts["har"] = str(har_path)
        if trace_path and trace_path.exists():
            try:
                self._artifacts["trace"] = str(trace_path.relative_to(self.session_dir))
            except Exception:
                self._artifacts["trace"] = str(trace_path)
        self._persist_metadata()
        return self.metadata_path

    def emergency_snapshot(self, reason: str) -> Optional[Path]:
        self._ended_at = self._ended_at or _iso_now()
        with self._metadata_lock:
            summary = self._build_summary()
            session_meta = summary.setdefault("session", {})
            session_meta.setdefault("status", "incomplete")
            session_meta["emergencyReason"] = reason
            try:
                self.metadata_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
                return self.metadata_path
            except Exception as exc:  # noqa: BLE001
                sys.stderr.write(f"[recorder] Failed to write emergency metadata snapshot: {exc}\n")
                return None


def _ensure_playwright() -> Playwright:
    try:
        return sync_playwright().start()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("Failed to start Playwright. Ensure `playwright install` has been run.") from exc


def _build_context(
    playwright: Playwright,
    browser_name: str,
    headless: bool,
    slow_mo: Optional[int],
    har_path: Optional[Path],
    ignore_https_errors: bool,
    user_agent: Optional[str] = None,
    proxy_server: Optional[str] = None,
    launch_args: Optional[List[str]] = None,
) -> BrowserContext:
    normalized_name = normalize_browser_name(browser_name, SUPPORTED_BROWSERS)
    browser_factory = getattr(playwright, normalized_name)
    launch_kwargs: Dict[str, Any] = {"headless": headless, "slow_mo": slow_mo}
    if proxy_server:
        # Playwright expects a dict with server key
        launch_kwargs["proxy"] = {"server": proxy_server}
    if launch_args:
        launch_kwargs["args"] = list(launch_args)
    browser: Browser = browser_factory.launch(**launch_kwargs)
    context_kwargs: Dict[str, Any] = {}
    if har_path:
        context_kwargs.update(
            record_har_path=str(har_path),
            record_har_mode="minimal",
        )
    if user_agent:
        context_kwargs["user_agent"] = user_agent
    context = browser.new_context(ignore_https_errors=ignore_https_errors, **context_kwargs)
    return context


def _await_user(timeout: Optional[int], stop_event: threading.Event) -> None:
    start = time.time()
    try:
        while not stop_event.is_set():
            time.sleep(0.2)
            if timeout and time.time() - start >= timeout:
                print(f"[recorder] Auto-stopping after {timeout} seconds.")
                stop_event.set()
                break
    except KeyboardInterrupt:
        print("\n[recorder] Stopping (Ctrl+C detected).")
        stop_event.set()


if __name__ == "__main__":
    # Allow graceful shutdown on Ctrl+C on Windows as well.
    try:
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    except (AttributeError, ValueError):
        pass
    main()

