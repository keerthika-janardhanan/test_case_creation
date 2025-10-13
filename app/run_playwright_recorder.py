"""Instrumented Playwright recorder that captures rich UI metadata for each action."""

from __future__ import annotations

import argparse
import json
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from playwright.sync_api import Browser, BrowserContext, Frame, Page, Playwright, sync_playwright


PAGE_INJECT_SCRIPT = """
(() => {
  const toText = node => (node && node.textContent ? node.textContent.trim().slice(0, 120) : "");

  const buildAncestors = element => {
    const chain = [];
    let current = element.parentElement;
    let depth = 0;
    while (current && depth < 8) {
      chain.push({
        tagName: current.tagName ? current.tagName.toLowerCase() : "",
        id: current.id || "",
        className: current.className || "",
        role: current.getAttribute ? (current.getAttribute("role") || "") : ""
      });
      current = current.parentElement;
      depth += 1;
    }
    return chain;
  };

  const siblingSummary = element => {
    if (!element || !element.parentElement) {
      return { previous: null, next: null, position: -1, total: 0 };
    }
    const siblings = Array.from(element.parentElement.children);
    const index = siblings.indexOf(element);
    const describe = node => {
      if (!node) return null;
      return {
        tagName: node.tagName ? node.tagName.toLowerCase() : "",
        text: toText(node),
        role: node.getAttribute ? (node.getAttribute("role") || "") : "",
        id: node.id || ""
      };
    };
    return {
      previous: describe(siblings[index - 1]),
      next: describe(siblings[index + 1]),
      position: index,
      total: siblings.length
    };
  };

  const findHeadingBackwards = node => {
    let current = node;
    while (current) {
      if (current.tagName && /^H[1-6]$/i.test(current.tagName)) {
        const text = toText(current);
        if (text) return text;
      }
      if (current.getAttribute && current.getAttribute("role") === "heading") {
        const text = toText(current);
        if (text) return text;
      }
      current = current.previousElementSibling;
    }
    return null;
  };

  const nearestHeading = element => {
    let cursor = element;
    while (cursor) {
      const heading = findHeadingBackwards(cursor.previousElementSibling);
      if (heading) return heading;
      cursor = cursor.parentElement;
    }
    const docHeading = document.querySelector("h1, h2, h3, [role='heading']");
    return docHeading ? toText(docHeading) : "";
  };

  const frameChain = () => {
    let frame = window.frameElement;
    const chain = [];
    while (frame) {
      chain.push({
        tagName: frame.tagName ? frame.tagName.toLowerCase() : "",
        name: frame.getAttribute ? (frame.getAttribute("name") || "") : "",
        id: frame.id || "",
        src: frame.getAttribute ? (frame.getAttribute("src") || "") : ""
      });
      const owner = frame.ownerDocument && frame.ownerDocument.defaultView;
      frame = owner ? owner.frameElement : null;
    }
    return chain;
  };

  const quadrant = (box, viewport) => {
    if (!box || !viewport) return "";
    const cx = box.x + box.width / 2;
    const cy = box.y + box.height / 2;
    const horizontal = cx < viewport.width / 2 ? "left" : "right";
    const vertical = cy < viewport.height / 2 ? "top" : "bottom";
    return `${vertical}-${horizontal}`;
  };

  const buildStableSelector = element => {
    if (!element) return "";
    if (element.hasAttribute && element.hasAttribute("data-testid")) {
      return `${element.tagName.toLowerCase()}[data-testid="${element.getAttribute("data-testid")}"]`;
    }
    if (element.id) {
      return `${element.tagName.toLowerCase()}#${element.id}`;
    }
    if (element.getAttribute && element.getAttribute("name")) {
      return `${element.tagName.toLowerCase()}[name="${element.getAttribute("name")}"]`;
    }
    if (element.classList && element.classList.length) {
      return `${element.tagName.toLowerCase()}.${Array.from(element.classList).slice(0, 3).join(".")}`;
    }
    return "";
  };

  const buildXPath = element => {
    if (!element || element.nodeType !== 1) return "";
    let xpath = "";
    let node = element;
    while (node && node.nodeType === 1) {
      let index = 1;
      let sibling = node.previousSibling;
      while (sibling) {
        if (sibling.nodeType === 1 && sibling.nodeName === node.nodeName) index += 1;
        sibling = sibling.previousSibling;
      }
      const tag = node.nodeName.toLowerCase();
      xpath = `/${tag}[${index}]` + xpath;
      node = node.parentNode && node.parentNode.nodeType === 1 ? node.parentNode : null;
    }
    return xpath;
  };

  const snapshotElement = element => {
    if (!element) return null;
    const rect = element.getBoundingClientRect();
    const dataAttributes = {};
    if (element.attributes) {
      for (const attr of Array.from(element.attributes)) {
        if (attr.name.startsWith("data-")) {
          dataAttributes[attr.name] = attr.value;
        }
      }
    }
    const root = element.getRootNode ? element.getRootNode() : null;
    const shadowHost = root && root.host ? root.host : null;
    const selectedOptions = [];
    if (element.tagName === "SELECT") {
      Array.from(element.selectedOptions || []).forEach(option => {
        selectedOptions.push({
          value: option.value,
          label: toText(option)
        });
      });
    }
    return {
      tagName: element.tagName ? element.tagName.toLowerCase() : "",
      role: element.getAttribute ? (element.getAttribute("role") || "") : "",
      ariaLabel: element.getAttribute ? (element.getAttribute("aria-label") || "") : "",
      ariaLabelledBy: element.getAttribute ? (element.getAttribute("aria-labelledby") || "") : "",
      placeholder: element.getAttribute ? (element.getAttribute("placeholder") || "") : "",
      title: element.getAttribute ? (element.getAttribute("title") || "") : "",
      text: toText(element),
      value: element.value !== undefined ? element.value : null,
      type: element.type || "",
      name: element.name || "",
      id: element.id || "",
      className: element.className || "",
      dataAttributes,
      checked: !!element.checked,
      disabled: !!element.disabled,
      href: element.getAttribute ? (element.getAttribute("href") || "") : "",
      boundingClientRect: {
        x: rect.x,
        y: rect.y,
        width: rect.width,
        height: rect.height
      },
      stableSelector: buildStableSelector(element),
      xpath: buildXPath(element),
      ancestors: buildAncestors(element),
      siblings: siblingSummary(element),
      nearestHeading: nearestHeading(element),
      frameChain: frameChain(),
      shadowHost: shadowHost ? {
        tagName: shadowHost.tagName ? shadowHost.tagName.toLowerCase() : "",
        id: shadowHost.id || "",
        className: shadowHost.className || ""
      } : null,
      selectedOptions
    };
  };

  const sendAction = (action, target, extra) => {
    if (!target || typeof window.pythonRecorderCapture !== "function") return;
    const element = snapshotElement(target);
    const viewport = {
      width: window.innerWidth,
      height: window.innerHeight,
      devicePixelRatio: window.devicePixelRatio || 1
    };
    const box = element && element.boundingClientRect ? element.boundingClientRect : null;
    window.pythonRecorderCapture({
      action,
      pageUrl: window.location.href,
      pageTitle: document.title,
      timestamp: Date.now(),
      viewport,
      element,
      extra: extra || {},
      boundingBox: box ? {
        x: box.x,
        y: box.y,
        width: box.width,
        height: box.height,
        quadrant: quadrant(box, viewport)
      } : null
    });
  };

  document.addEventListener("click", event => {
    sendAction("click", event.target, { button: event.button });
  }, true);

  document.addEventListener("change", event => {
    const target = event.target;
    const payload = {};
    if (target && target.value !== undefined) {
      payload.value = target.value;
    }
    if (target && target.tagName === "SELECT") {
      payload.selectedOptions = Array.from(target.selectedOptions || []).map(opt => ({
        value: opt.value,
        label: toText(opt)
      }));
    }
    sendAction("change", event.target, payload);
  }, true);

  document.addEventListener("input", event => {
    const target = event.target;
    const payload = {};
    if (target && target.value !== undefined) {
      payload.value = target.value;
    }
    sendAction("input", event.target, payload);
  }, true);

  document.addEventListener("focus", event => {
    sendAction("focus", event.target, {});
  }, true);

  document.addEventListener("keydown", event => {
    const interesting = ["Enter", "Escape", "Tab", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"];
    if (interesting.includes(event.key)) {
      sendAction("press", event.target, {
        key: event.key,
        code: event.code,
        metaKey: event.metaKey,
        ctrlKey: event.ctrlKey,
        altKey: event.altKey,
        shiftKey: event.shiftKey
      });
    }
  }, true);

  const sendPageContext = () => {
    if (typeof window.pythonRecorderPageContext !== "function") return;
    const breadcrumbSelectors = [
      "[data-breadcrumb]",
      "nav .breadcrumb li",
      ".breadcrumb li",
      "nav[aria-label='Breadcrumb'] *"
    ];
    const breadcrumbs = [];
    breadcrumbSelectors.forEach(selector => {
      document.querySelectorAll(selector).forEach(node => {
        const text = toText(node);
        if (text) breadcrumbs.push(text);
      });
    });
    window.pythonRecorderPageContext({
      pageUrl: window.location.href,
      title: document.title,
      breadcrumbs,
      timestamp: Date.now(),
      viewport: {
        width: window.innerWidth,
        height: window.innerHeight,
        devicePixelRatio: window.devicePixelRatio || 1
      }
    });
  };

  document.addEventListener("DOMContentLoaded", () => sendPageContext());
  window.addEventListener("hashchange", () => sendPageContext());
  window.addEventListener("popstate", () => sendPageContext());
  window.addEventListener("resize", () => sendPageContext());
  sendPageContext();
  if (typeof console !== "undefined") {
    console.log("[recorder] instrumentation attached");
  }
})();
"""


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
    ) -> None:
        self.session_dir = session_dir
        self.capture_dom = capture_dom
        self.capture_screenshots = capture_screenshots
        self.stop_event = stop_event
        self.actions: List[Dict[str, Any]] = []
        self.page_events: List[Dict[str, Any]] = []
        self.action_counter = 0
        self.started_at = _iso_now()
        self.screenshot_dir = self.session_dir / "screenshots"
        self.dom_dir = self.session_dir / "dom"
        self._page_lock = threading.Lock()
        self._pages: Dict[int, Page] = {}
        self._last_page_id: Optional[int] = None
        if self.capture_screenshots:
            self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        if self.capture_dom:
            self.dom_dir.mkdir(parents=True, exist_ok=True)

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

    def handle_page_context(self, _source: Any, payload: Dict[str, Any]) -> None:
        event = dict(payload or {})
        event["receivedAt"] = _iso_now()
        self.page_events.append(event)

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

    def finalize(self, options: Dict[str, Any], har_path: Optional[Path], trace_path: Optional[Path]) -> Path:
        summary = {
            "session": {
                "id": self.session_dir.name,
                "startedAt": self.started_at,
                "endedAt": _iso_now(),
            },
            "options": options,
            "pageContextEvents": self.page_events,
            "actions": self.actions,
            "artifacts": {
                "har": str(har_path.relative_to(self.session_dir)) if har_path and har_path.exists() else None,
                "trace": str(trace_path.relative_to(self.session_dir)) if trace_path and trace_path.exists() else None,
            },
        }
        output_path = self.session_dir / "metadata.json"
        output_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return output_path


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
) -> BrowserContext:
    browser_factory = getattr(playwright, browser_name)
    browser: Browser = browser_factory.launch(headless=headless, slow_mo=slow_mo)
    context_kwargs: Dict[str, Any] = {}
    if har_path:
        context_kwargs.update(
            record_har_path=str(har_path),
            record_har_mode="minimal",
        )
    context = browser.new_context(**context_kwargs)
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Launch an instrumented Playwright browser that records rich UI metadata for manual test generation."
    )
    parser.add_argument("--url", required=True, help="Initial URL to open in the recorder session.")
    parser.add_argument("--output-dir", default="recordings", help="Base directory to store recording artifacts.")
    parser.add_argument("--session-name", default=None, help="Optional name for the recording session directory.")
    parser.add_argument("--browser", choices=["chromium", "firefox", "webkit"], default="chromium", help="Browser engine to use.")
    parser.add_argument("--headless", action="store_true", help="Run the browser in headless mode.")
    parser.add_argument("--slow-mo", type=int, default=None, help="Slow down Playwright actions by the given milliseconds.")
    parser.add_argument("--timeout", type=int, default=None, help="Automatically stop the recorder after N seconds.")
    parser.add_argument("--no-trace", action="store_true", help="Disable Playwright trace capture.")
    parser.add_argument("--no-har", action="store_true", help="Disable HAR/network capture.")
    parser.add_argument("--capture-dom", action="store_true", help="Persist DOM snapshot HTML for each captured action.")
    parser.add_argument("--capture-screenshots", action="store_true", help="Capture element screenshots for each action.")

    args = parser.parse_args()

    output_root = Path(args.output_dir).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    session_name = args.session_name or datetime.now().strftime("%Y%m%d_%H%M%S")
    session_dir = output_root / session_name
    session_dir.mkdir(parents=True, exist_ok=True)

    har_path: Optional[Path] = None
    trace_path: Optional[Path] = None

    print(f"[recorder] Session directory: {session_dir}")
    print(f"[recorder] Launching browser ({args.browser}) at {args.url}")
    if args.timeout:
        print(f"[recorder] Session will auto-stop after {args.timeout} seconds or when you press Ctrl+C.")
    else:
        print("[recorder] Press Ctrl+C in this terminal to stop recording.")

    playwright = _ensure_playwright()
    context = None
    browser = None
    stop_event = threading.Event()
    session: Optional[RecorderSession] = None
    try:
        if not args.no_har:
            har_path = session_dir / "network.har"

        context = _build_context(
            playwright=playwright,
            browser_name=args.browser,
            headless=args.headless,
            slow_mo=args.slow_mo,
            har_path=har_path if not args.no_har else None,
        )
        browser = context.browser

        session = RecorderSession(
            session_dir=session_dir,
            capture_dom=args.capture_dom,
            capture_screenshots=args.capture_screenshots,
            stop_event=stop_event,
        )

        def _on_page(new_page: Page) -> None:
            session.register_page(new_page)
            try:
                def _handle_close() -> None:
                    session.unregister_page(new_page)
                    stop_event.set()

                new_page.once("close", _handle_close)
            except Exception:
                pass

        context.on("page", _on_page)
        try:
            context.once("close", lambda: stop_event.set())
        except Exception:
            pass

        context.expose_binding("pythonRecorderCapture", session.handle_capture)
        context.expose_binding("pythonRecorderPageContext", session.handle_page_context)
        context.add_init_script(PAGE_INJECT_SCRIPT)

        page = context.new_page()
        _on_page(page)

        tracer = context.tracing
        if not args.no_trace:
            trace_path = session_dir / "trace.zip"
            tracer.start(screenshots=True, snapshots=True, sources=True)

        page.goto(args.url, wait_until="domcontentloaded")

        _await_user(args.timeout, stop_event)

        if not args.no_trace and trace_path:
            try:
                tracer.stop(path=str(trace_path))
            except KeyboardInterrupt:
                stop_event.set()
                sys.stderr.write("[recorder] Trace stop interrupted.\n")
            except Exception as exc:  # noqa: BLE001
                message = str(exc)
                if "Target page" in message or "Browser has been closed" in message:
                    sys.stderr.write("[recorder] Trace already closed when stopping (browser closed first).\n")
                else:
                    sys.stderr.write(f"[recorder] Failed to stop tracing: {exc}\n")

        context.close()
        browser.close()
        playwright.stop()

        options = {
            "browser": args.browser,
            "headless": args.headless,
            "slowMo": args.slow_mo,
            "captureDom": args.capture_dom,
            "captureScreenshots": args.capture_screenshots,
            "recordHar": not args.no_har,
            "recordTrace": not args.no_trace,
            "url": args.url,
        }
        metadata_path = session.finalize(options=options, har_path=har_path, trace_path=trace_path)

        print(f"[recorder] Recorded {len(session.actions)} actions.")
        print(f"[recorder] Metadata saved to {metadata_path}")
        if har_path and har_path.exists():
            print(f"[recorder] HAR saved to {har_path}")
        if trace_path and trace_path.exists():
            print(f"[recorder] Trace saved to {trace_path}")
        if session.capture_dom:
            print(f"[recorder] DOM snapshots stored in {session.dom_dir}")
        if session.capture_screenshots:
            print(f"[recorder] Screenshots stored in {session.screenshot_dir}")
    except KeyboardInterrupt:
        stop_event.set()
        sys.stderr.write("[recorder] Interrupt received. Cleaning up...\n")
    finally:
        # Ensure Playwright is stopped even if exceptions bubble up
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


if __name__ == "__main__":
    # Allow graceful shutdown on Ctrl+C on Windows as well.
    try:
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    except (AttributeError, ValueError):
        pass
    main()
