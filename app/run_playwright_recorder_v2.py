"""Recorder v2: simplified, reliable Playwright recorder with robust navigation.

Artifacts per session:
  recordings/<session>/
    - metadata.json
    - dom/*.html              (with --capture-dom)
    - screenshots/*.png       (with --capture-screenshots)
    - network.har             (unless --no-har)
    - trace.zip               (unless --no-trace)

Usage (PowerShell):
  python -m app.run_playwright_recorder_v2 --url "https://example.com" --capture-dom --timeout 20
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
from typing import Any, Dict, List, Optional
from collections import deque

from playwright.sync_api import (
    Browser,
    BrowserContext,
    ConsoleMessage,
    Frame,
    Page,
    Playwright,
    sync_playwright,
)

from app.browser_utils import SUPPORTED_BROWSERS, normalize_browser_name

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

PAGE_INJECT_SCRIPT = """
(() => {
    try { if (window.__pyRecInstalled) { return; } window.__pyRecInstalled = true; } catch(_) {}
    const deliver = (name, payload) => { const fn = window && window[name]; if (typeof fn === 'function') { fn(payload); return true; } return false; };
    const capQ = []; const ctxQ = [];
    const sendCap = p => { if (!deliver('pythonRecorderCapture', p)) capQ.push(p); };
    const sendCtxI = p => { if (!deliver('pythonRecorderPageContext', p)) ctxQ.push(p); };
    setInterval(() => { while (capQ.length && deliver('pythonRecorderCapture', capQ[0])) capQ.shift(); while (ctxQ.length && deliver('pythonRecorderPageContext', ctxQ[0])) ctxQ.shift(); }, 200);
    const norm = n => (n && n.nodeType === Node.TEXT_NODE ? n.parentElement : (n && n.nodeType === Node.ELEMENT_NODE ? n : null));
    const targetOf = e => { try { if (e && typeof e.composedPath === 'function') { const p = e.composedPath(); if (p && p.length) { return p[0]; } } } catch(_) {} return e ? e.target : null; };
    const xp = el => { if (!el || el.nodeType !== 1) return ''; const s=[]; let n=el; while(n&&n.nodeType===1){let i=1;let b=n.previousSibling;while(b){if(b.nodeType===1&&b.nodeName===n.nodeName)i++; b=b.previousSibling;} s.unshift(`${n.nodeName.toLowerCase()}[${i}]`); n=n.parentNode&&n.parentNode.nodeType===1?n.parentNode:null;} return '/' + s.join('/'); };
    const css = el => { const parts=[]; let n=el; while(n&&n.nodeType===1){ let sel=n.nodeName.toLowerCase(); if(n.id){parts.unshift(`${sel}#${n.id}`);break;} const p=n.parentNode; if(!p) break; const i=Array.from(p.children).indexOf(n)+1; parts.unshift(`${sel}:nth-child(${i})`); n=p;} return parts.join(' > '); };
    const snap = raw => { const el = norm(raw); if (!el) return null; let r=null; try{ r=el.getBoundingClientRect(); }catch(e){} return { tag: (el.tagName||'').toLowerCase(), id: el.id||'', className: el.className||'', text: (el && el.textContent ? el.textContent.trim().slice(0,120) : ''), xpath: xp(el), cssPath: css(el), rect: r?{x:r.x,y:r.y,width:r.width,height:r.height}:null }; };
    const send = (action, target, extra) => { const element = snap(target); const payload = { action, pageUrl: location.href, pageTitle: document.title, timestamp: Date.now(), element, extra: extra||{} }; try { console.debug('[recorder] action', action, element && element.tag || '', location.href); } catch(_) {} sendCap(payload); };
    // Broader events (Shadow DOM aware via composedPath)
    document.addEventListener('click', e => send('click', targetOf(e), {button:e.button}), true);
    document.addEventListener('dblclick', e => send('dblclick', targetOf(e), {button:e.button}), true);
    document.addEventListener('contextmenu', e => send('contextmenu', targetOf(e), {button:e.button}), true);
    document.addEventListener('pointerdown', e => send('pointerdown', targetOf(e), {button:e.button, pointerType:e.pointerType||''}), true);
    document.addEventListener('pointerup', e => send('pointerup', targetOf(e), {button:e.button, pointerType:e.pointerType||''}), true);
    document.addEventListener('focus', e => send('focus', targetOf(e), {}), true);
    document.addEventListener('blur', e => send('blur', targetOf(e), {}), true);
    document.addEventListener('submit', e => { const f=targetOf(e); const act={}; try{ act.action=f.action||''; act.method=f.method||''; }catch(_){} send('submit', f, act); }, true);
    const isSensitive = (el) => {
        const idn = (el && (el.name || el.id || '') || '').toLowerCase();
        const type = (el && el.type || '').toLowerCase();
        if (type === 'password') return true;
        return /password|pwd|otp|token|secret|pin/.test(idn);
    };
    document.addEventListener('change', e => { const t=targetOf(e); const masked=isSensitive(t); const val=t&&t.value; send('change', t, { value: masked ? '<masked>' : val, valueMasked: !!masked }); }, true);
    document.addEventListener('input', e => { const t=targetOf(e); const masked=isSensitive(t); const val=t&&t.value; send('input', t, { value: masked ? '<masked>' : val, valueMasked: !!masked }); }, true);
    document.addEventListener('keydown', e => { const keys=['Enter','Escape','Tab','ArrowUp','ArrowDown','ArrowLeft','ArrowRight']; if (keys.includes(e.key)) send('press', targetOf(e), {key:e.key, code:e.code}); }, true);
    document.addEventListener('keyup', e => { const keys=['Enter','Escape','Tab']; if (keys.includes(e.key)) send('keyrelease', targetOf(e), {key:e.key, code:e.code}); }, true);
    // Throttled wheel capture (scroll)
    let __lastWheel = 0;
    document.addEventListener('wheel', e => {
        const now = Date.now();
        if (now - __lastWheel > 300) {
            __lastWheel = now;
            send('wheel', targetOf(e), { deltaX: e.deltaX, deltaY: e.deltaY });
        }
    }, { capture: true, passive: true });
    const sendCtx = (trigger) => { const payload = { pageUrl: location.href, title: document.title, timestamp: Date.now(), trigger }; sendCtxI(payload); };
    document.addEventListener('DOMContentLoaded', () => sendCtx('domcontentloaded'));
    window.addEventListener('load', () => sendCtx('load'));
    // SPA route changes
    const _origPushState = history.pushState; const _origReplaceState = history.replaceState;
    history.pushState = function() { try { const r = _origPushState.apply(this, arguments); setTimeout(() => sendCtx('pushstate'), 0); return r; } catch(e) { return _origPushState.apply(this, arguments); } };
    history.replaceState = function() { try { const r = _origReplaceState.apply(this, arguments); setTimeout(() => sendCtx('replacestate'), 0); return r; } catch(e) { return _origReplaceState.apply(this, arguments); } };
    window.addEventListener('hashchange', () => sendCtx('hashchange'));
    sendCtx('init');
})();
"""


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RecorderSession:
    def __init__(self, session_dir: Path, capture_dom: bool, capture_screenshots: bool, options: Dict[str, Any]) -> None:
        self.session_dir = session_dir
        self.capture_dom = capture_dom
        self.capture_screenshots = capture_screenshots
        self.options = dict(options)
        self.actions: List[Dict[str, Any]] = []
        self.page_events: List[Dict[str, Any]] = []
        self.metadata_path = self.session_dir / "metadata.json"
        self.dom_dir = self.session_dir / "dom"
        self.screenshot_dir = self.session_dir / "screenshots"
        if self.capture_dom:
            self.dom_dir.mkdir(parents=True, exist_ok=True)
        if self.capture_screenshots:
            self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self.started_at = _iso_now()
        self.ended_at: Optional[str] = None
        self.artifacts: Dict[str, Optional[str]] = {"har": None, "trace": None}
        self._persist()

    def _persist(self) -> None:
        summary = {
            "session": {"id": self.session_dir.name, "startedAt": self.started_at, **({"endedAt": self.ended_at} if self.ended_at else {})},
            "options": self.options,
            "pageContextEvents": self.page_events,
            "actions": self.actions,
            "artifacts": self.artifacts,
        }
        try:
            self.metadata_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        except Exception:
            pass

    def add_page_event(self, payload: Dict[str, Any]) -> None:
        data = dict(payload or {})
        data["receivedAt"] = _iso_now()
        self.page_events.append(data)
        self._persist()

    def add_action(self, payload: Dict[str, Any]) -> None:
        data = dict(payload or {})
        data["receivedAt"] = _iso_now()
        self.actions.append(data)
        self._persist()

    def finalize(self, har_path: Optional[Path], trace_path: Optional[Path]) -> Path:
        self.ended_at = _iso_now()
        if har_path and har_path.exists():
            try:
                self.artifacts["har"] = str(har_path.relative_to(self.session_dir))
            except Exception:
                self.artifacts["har"] = str(har_path)
        if trace_path and trace_path.exists():
            try:
                self.artifacts["trace"] = str(trace_path.relative_to(self.session_dir))
            except Exception:
                self.artifacts["trace"] = str(trace_path)
        self._persist()
        return self.metadata_path


def _ensure_playwright() -> Playwright:
    return sync_playwright().start()


def _wait_bindings_ready(p: Optional[Page], timeout_ms: int = 5000) -> None:
    """Best-effort wait that our injected recorder bindings are ready on the page.

    This reduces missed early actions caused by race conditions where the page is interactive
    before the init script runs. Safe to call even if the page is closing.
    """
    if not p or p.is_closed():
        return
    try:
        # Nudge the page to ensure scripts run, then wait for our flag.
        try:
            p.evaluate("() => { try { return !!window.__pyRecInstalled; } catch(_) { return false; } }")
        except Exception:
            pass
        p.wait_for_function("() => window.__pyRecInstalled === true", timeout=timeout_ms)
    except Exception:
        # Non-fatal: on some pages (e.g., cross-origin iframes) this may not be reachable
        pass


def _silence_bindings_on_pages(ctx: Optional[BrowserContext]) -> None:
    """Replace exposed bindings with no-ops to stop cross-process calls during shutdown."""
    if not ctx:
        return
    pages: List[Page]
    try:
        pages = list(getattr(ctx, "pages", []))
    except Exception:
        pages = []
    for p in pages:
        try:
            if p and not p.is_closed():
                p.evaluate(
                    """
                    () => {
                        try {
                            window.__pyRecInstalledStopped = true;
                            window.pythonRecorderCapture = () => {};
                            window.pythonRecorderPageContext = () => {};
                        } catch (_) {}
                    }
                    """
                )
        except Exception:
            pass


def _build_context(
    playwright: Playwright,
    browser_name: str,
    headless: bool,
    slow_mo: Optional[int],
    har_path: Optional[Path],
    ignore_https_errors: bool,
    user_agent: Optional[str],
    proxy_server: Optional[str] = None,
    launch_args: Optional[List[str]] = None,
) -> BrowserContext:
    name = normalize_browser_name(browser_name, SUPPORTED_BROWSERS)
    factory = getattr(playwright, name)
    launch_kwargs: Dict[str, Any] = {"headless": headless, "slow_mo": slow_mo}
    if proxy_server:
        launch_kwargs["proxy"] = {"server": proxy_server}
    if launch_args:
        launch_kwargs["args"] = list(launch_args)
    browser: Browser = factory.launch(**launch_kwargs)
    ctx_kwargs: Dict[str, Any] = {"ignore_https_errors": ignore_https_errors}
    if har_path:
        ctx_kwargs.update(record_har_path=str(har_path), record_har_mode="minimal")
    if user_agent:
        ctx_kwargs["user_agent"] = user_agent
    return browser.new_context(**ctx_kwargs)


# Console/page/network diagnostics

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


def main() -> None:
    parser = argparse.ArgumentParser(description="Reliable Playwright recorder with robust navigation.")
    parser.add_argument("--url", required=True)
    parser.add_argument("--output-dir", default="recordings")
    parser.add_argument("--session-name", default=None)
    parser.add_argument("--browser", default="chromium")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--slow-mo", type=int, default=None)
    parser.add_argument("--timeout", type=int, default=None)
    parser.add_argument("--no-trace", action="store_true")
    parser.add_argument("--no-har", action="store_true")
    parser.add_argument("--capture-dom", action="store_true")
    parser.add_argument("--capture-screenshots", action="store_true")
    parser.add_argument("--ignore-https-errors", action="store_true")
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    parser.add_argument("--proxy")
    parser.add_argument("--disable-gpu", action="store_true")

    args = parser.parse_args()
    try:
        args.browser = normalize_browser_name(args.browser, SUPPORTED_BROWSERS)
    except ValueError as exc:
        parser.error(str(exc))

    output_root = Path(args.output_dir).resolve(); output_root.mkdir(parents=True, exist_ok=True)
    session_name = args.session_name or datetime.now().strftime("%Y%m%d_%H%M%S")
    session_dir = output_root / session_name; session_dir.mkdir(parents=True, exist_ok=True)

    print(f"[recorder] Session directory: {session_dir}")
    print(f"[recorder] Launching browser ({args.browser}) at {args.url}")
    if args.timeout:
        print(f"[recorder] Auto-stop after {args.timeout} seconds or Ctrl+C.")
    else:
        print("[recorder] Press Ctrl+C to stop recording.")

    playwright = _ensure_playwright()
    context: Optional[BrowserContext] = None
    browser: Optional[Browser] = None
    stop_event = threading.Event()
    # Graceful shutdown handlers
    try:
        signal.signal(signal.SIGINT, lambda *_: stop_event.set())
    except (AttributeError, ValueError):
        pass
    try:
        signal.signal(signal.SIGTERM, lambda *_: stop_event.set())
    except (AttributeError, ValueError):
        pass
    # Windows: SIGBREAK when CTRL+BREAK is sent
    try:
        if hasattr(signal, "SIGBREAK"):
            signal.signal(signal.SIGBREAK, lambda *_: stop_event.set())
    except (AttributeError, ValueError):
        pass

    har_path: Optional[Path] = None
    trace_path: Optional[Path] = None
    metadata_written = False
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
            ignore_https_errors=args.ignore_https_errors,
            user_agent=args.user_agent,
            proxy_server=args.proxy,
            launch_args=["--disable-gpu", "--disable-software-rasterizer"] if args.disable_gpu and args.browser == "chromium" else None,
        )
        browser = context.browser

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
                "proxy": args.proxy,
                "disableGpu": args.disable_gpu,
            },
        )

        # Queues to avoid Playwright API calls inside binding callbacks (deadlock risk)
        pending_actions = deque()
        pending_ctx = deque()
        q_lock = threading.Lock()
        # Track current page for artifact capture; update on popups or navigation
        active_page: Optional[Page] = None

        def _enqueue_action(_source, payload):
            if stop_event.is_set():
                return
            with q_lock:
                item = dict(payload or {})
                try:
                    # Attach page/frame references for later capture (not persisted)
                    fr = getattr(_source, "frame", None)
                    pg = getattr(_source, "page", None) or (fr.page if getattr(fr, "page", None) else None)
                    if fr is not None:
                        item["__frame"] = fr
                    if pg is not None:
                        item["__page"] = pg
                except Exception:
                    pass
                pending_actions.append(item)

        def _enqueue_ctx(_source, payload):
            if stop_event.is_set():
                return
            with q_lock:
                item = dict(payload or {})
                try:
                    fr = getattr(_source, "frame", None)
                    pg = getattr(_source, "page", None) or (fr.page if getattr(fr, "page", None) else None)
                    if fr is not None:
                        item["__frame"] = fr
                    if pg is not None:
                        item["__page"] = pg
                except Exception:
                    pass
                pending_ctx.append(item)

        context.expose_binding("pythonRecorderCapture", _enqueue_action)
        context.expose_binding("pythonRecorderPageContext", _enqueue_ctx)
        context.add_init_script(PAGE_INJECT_SCRIPT)

        # Diagnostics
        def _on_requestfailed(req):
            reason = ""
            try:
                failure = req.failure(); reason = failure.get("errorText") if isinstance(failure, dict) else str(failure)
            except Exception:
                reason = ""
            sys.stderr.write(f"[recorder][requestfailed] {req.url} -> {reason}\n")
        context.on("requestfailed", _on_requestfailed)

        page = context.new_page()
        active_page = page
        try:
            page.add_init_script(PAGE_INJECT_SCRIPT)
        except Exception:
            pass
        # Ensure our bindings are live before user interactions
        _wait_bindings_ready(page)
        # Console handler with fallback action capture if bindings fail
        # Track recent pointerdown to synthesize a click if navigation interrupts the native click event
        _last_pointerdown: Dict[str, Any] = {"url": None, "tag": None, "t": 0.0}

        def _on_console_with_fallback(msg: ConsoleMessage) -> None:
            try:
                text = msg.text
                sys.stderr.write(f"[recorder][console] {msg.type}: {text}\n")
                # Fallback: parse our own debug logs to recover an action if bindings failed
                if session and isinstance(text, str) and text.startswith("[recorder] action"):
                    # Format: "[recorder] action <action> <tag> <url>"
                    parts = text.split()
                    if len(parts) >= 5:
                        act = parts[2]
                        tag = parts[3]
                        url = parts[4]
                        now = time.time()
                        # record the raw action
                        fallback = {"action": act, "pageUrl": url, "element": {"tag": tag}, "extra": {"fromConsole": True}}
                        try:
                            session.add_action(fallback)
                        except Exception:
                            pass
                        # synthesize a click if pointerdown was seen shortly before pointerup and no click surfaced
                        try:
                            if act == "pointerdown":
                                _last_pointerdown.update({"url": url, "tag": tag, "t": now})
                            elif act == "pointerup":
                                last_t = float(_last_pointerdown.get("t") or 0.0)
                                last_url = _last_pointerdown.get("url")
                                if last_t and (now - last_t) <= 0.6 and (not last_url or last_url == url):
                                    synth = {"action": "click", "pageUrl": url, "element": {"tag": tag}, "extra": {"synthesized": True, "fromConsole": True}}
                                    session.add_action(synth)
                                _last_pointerdown.update({"url": None, "tag": None, "t": 0.0})
                        except Exception:
                            pass
            except Exception:
                pass
        page.on("console", _on_console_with_fallback)
        page.on("pageerror", _on_page_error)
        # Inject into frames when attached (defensive; context.add_init_script usually covers this)
        try:
            def _on_frame_attached(f: Frame) -> None:
                try:
                    f.add_script_tag(content=PAGE_INJECT_SCRIPT)
                except Exception:
                    pass
            page.on("frameattached", _on_frame_attached)
        except Exception:
            pass
        try:
            def _on_popup(p: Page) -> None:
                nonlocal active_page
                active_page = p
                try:
                    p.add_init_script(PAGE_INJECT_SCRIPT)
                except Exception:
                    pass
                _wait_bindings_ready(p)
                try:
                    p.on("framenavigated", lambda f: sys.stderr.write(f"[recorder][framenavigated] {getattr(f, 'url', '')}\n"))
                except Exception:
                    pass
                try:
                    p.on("frameattached", _on_frame_attached)
                except Exception:
                    pass
                sys.stderr.write(f"[recorder][popup] {getattr(p, 'url', lambda: '')()}\n")
            page.on("popup", _on_popup)
        except Exception:
            pass

        # Also instrument new pages created via window.open or login redirects
        try:
            def _on_new_page(p: Page) -> None:
                nonlocal active_page
                active_page = p
                try:
                    p.add_init_script(PAGE_INJECT_SCRIPT)
                except Exception:
                    pass
                _wait_bindings_ready(p)
                p.on("console", _on_console_with_fallback)
                p.on("pageerror", _on_page_error)
                try:
                    p.on("framenavigated", lambda f: sys.stderr.write(f"[recorder][framenavigated] {getattr(f, 'url', '')}\n"))
                except Exception:
                    pass
                try:
                    p.on("frameattached", _on_frame_attached)
                except Exception:
                    pass
            context.on("page", _on_new_page)
        except Exception:
            pass
        try:
            page.on("framenavigated", lambda f: sys.stderr.write(f"[recorder][framenavigated] {getattr(f, 'url', '')}\n"))
        except Exception:
            pass

        # Trace
        tracer = context.tracing
        if not args.no_trace:
            trace_path = session_dir / "trace.zip"
            tracer.start(screenshots=True, snapshots=True, sources=True)

        # Navigate with fallback
        nav_ok = False
        try:
            page.goto(args.url, wait_until="domcontentloaded")
            nav_ok = True
        except Exception as nav_exc:  # noqa: BLE001
            sys.stderr.write(f"[recorder] page.goto failed: {nav_exc}\n")
            try:
                page.evaluate("url => window.location.assign(url)", args.url)
                page.wait_for_load_state("domcontentloaded", timeout=15000)
                nav_ok = True
            except Exception as eval_exc:  # noqa: BLE001
                sys.stderr.write(f"[recorder] Fallback failed: {eval_exc}\n")

        if nav_ok:
            try:
                page.wait_for_load_state("load", timeout=20000)
            except Exception:
                pass

        # Helpers for safe capture on the main thread
        def _safe_get_outer_html(p: Optional[Page]) -> Optional[str]:
            if not p or p.is_closed():
                return None
            try:
                return p.content()
            except Exception:
                try:
                    return p.evaluate("() => document.documentElement.outerHTML")
                except Exception:
                    return None

        def _safe_screenshot(p: Optional[Page], path: Path, clip: Optional[Dict[str, float]] = None) -> Optional[str]:
            if not p or p.is_closed():
                return None
            try:
                if clip:
                    p.screenshot(path=str(path), clip=clip)
                else:
                    p.screenshot(path=str(path), full_page=True)
                return str(path)
            except Exception:
                try:
                    p.screenshot(path=str(path), full_page=True)
                    return str(path)
                except Exception:
                    return None

        # Wait loop
        start = time.time()
        try:
            while not stop_event.is_set():
                # Drain queues
                try:
                    # Process page context events first (may create P-### artifacts)
                    while True:
                        with q_lock:
                            evt = pending_ctx.popleft() if pending_ctx else None
                        if not evt:
                            break
                        # Decide whether to capture artifacts on dom milestone
                        should_snap = evt.get("trigger") in {"domcontentloaded", "load"}
                        if should_snap and (args.capture_dom or args.capture_screenshots):
                            # Give layout a brief moment to settle to avoid blank screenshots
                            try:
                                time.sleep(0.15)
                            except Exception:
                                pass
                            ap = active_page if (active_page and not active_page.is_closed()) else (page if (page and not page.is_closed()) else None)
                            # DOM
                            if args.capture_dom:
                                html = _safe_get_outer_html(ap)
                                if html is not None:
                                    idxp = len(session.page_events) + 1
                                    dp = session.dom_dir / f"P-{idxp:03}.html"
                                    dp.write_text(str(html), encoding="utf-8")
                                    evt["domSnapshotPath"] = str(dp.relative_to(session.session_dir))
                                else:
                                    evt["domSnapshotError"] = "no-html"
                            # Screenshot
                            if args.capture_screenshots:
                                idxp = len(session.page_events) + 1
                                sp = session.screenshot_dir / f"P-{idxp:03}.png"
                                spath = _safe_screenshot(ap, sp)
                                if spath:
                                    evt["screenshotPath"] = str(Path(spath).relative_to(session.session_dir))
                                else:
                                    evt["screenshotError"] = "shot-failed"
                        session.add_page_event(evt)

                    # Process actions
                    while True:
                        with q_lock:
                            act = pending_actions.popleft() if pending_actions else None
                        if not act:
                            break
                        # Pull internal references and strip them from the record before persisting
                        frame_ref = act.pop("__frame", None)
                        page_ref = act.pop("__page", None)
                        if args.capture_dom or args.capture_screenshots:
                            ap = active_page if (active_page and not active_page.is_closed()) else (page if (page and not page.is_closed()) else None)
                            idxa = len(session.actions) + 1
                            # DOM
                            if args.capture_dom:
                                html = None
                                # Prefer frame DOM if available
                                try:
                                    if frame_ref is not None and not frame_ref.is_detached():
                                        try:
                                            html = frame_ref.content()
                                        except Exception:
                                            html = None
                                except Exception:
                                    html = None
                                if html is None:
                                    html = _safe_get_outer_html(ap)
                                if html is not None:
                                    da = session.dom_dir / f"A-{idxa:03}.html"
                                    da.write_text(str(html), encoding="utf-8")
                                    act["domSnapshotPath"] = str(da.relative_to(session.session_dir))
                                else:
                                    act["domSnapshotError"] = "no-html"
                            # Screenshot
                            if args.capture_screenshots:
                                sa = session.screenshot_dir / f"A-{idxa:03}.png"
                                clip = None
                                try:
                                    rect = ((act.get("element") or {}).get("rect") or None)
                                    if rect and all(k in rect for k in ("x", "y", "width", "height")):
                                        w = max(1, float(rect.get("width", 1)))
                                        h = max(1, float(rect.get("height", 1)))
                                        x = max(0, float(rect.get("x", 0)))
                                        y = max(0, float(rect.get("y", 0)))
                                        if w >= 2 and h >= 2:
                                            clip = {"x": x, "y": y, "width": w, "height": h}
                                except Exception:
                                    clip = None
                                spath = _safe_screenshot(ap, sa, clip)
                                if spath:
                                    act["screenshotPath"] = str(Path(spath).relative_to(session.session_dir))
                                else:
                                    act["screenshotError"] = "shot-failed"
                        # Add useful context
                        try:
                            if frame_ref is not None:
                                act.setdefault("frameUrl", frame_ref.url)
                        except Exception:
                            pass
                        try:
                            if (page_ref or active_page) and (page_ref or page):
                                pref = page_ref or active_page or page
                                act.setdefault("pageUrl", act.get("pageUrl") or getattr(pref, "url", ""))
                        except Exception:
                            pass
                        session.add_action(act)
                except Exception as drain_exc:
                    sys.stderr.write(f"[recorder] drain error: {drain_exc}\n")

                time.sleep(0.2)
                if args.timeout and time.time() - start >= args.timeout:
                    print(f"[recorder] Auto-stopping after {args.timeout} seconds.")
                    stop_event.set(); break
        except KeyboardInterrupt:
            print("\n[recorder] Stopping (Ctrl+C detected).")
            stop_event.set()

        # Stop JS-to-Python calls before we drain to reduce socket errors during teardown
        try:
            _silence_bindings_on_pages(context)
        except Exception:
            pass

        # Final aggressive drain to avoid dropping last actions when stopping
        try:
            # small settle to allow in-flight JS messages to reach bindings
            try:
                time.sleep(0.2)
            except Exception:
                pass

            end_deadline = time.time() + 2.0  # allow up to 2s to flush
            empty_cycles = 0
            while time.time() < end_deadline and empty_cycles < 3:
                drained_any = False
                # Drain context events fully
                while True:
                    with q_lock:
                        evt = pending_ctx.popleft() if pending_ctx else None
                    if not evt:
                        break
                    try:
                        session.add_page_event(evt)
                    except Exception:
                        pass
                    drained_any = True
                # Drain action events fully
                while True:
                    with q_lock:
                        act = pending_actions.popleft() if pending_actions else None
                    if not act:
                        break
                    # Strip any internal refs and persist minimal payload
                    act.pop("__frame", None); act.pop("__page", None)
                    try:
                        session.add_action(act)
                    except Exception:
                        pass
                    drained_any = True
                if not drained_any:
                    empty_cycles += 1
                else:
                    empty_cycles = 0
                try:
                    time.sleep(0.05)
                except Exception:
                    pass
        except Exception:
            pass

        # Final best-effort snapshot so the last UI state is present even if no page event fired
        try:
            if session and (args.capture_dom or args.capture_screenshots):
                ap = active_page if (active_page and not active_page.is_closed()) else (page if (page and not page.is_closed()) else None)
                if ap:
                    finalize_evt: Dict[str, Any] = {"trigger": "finalize", "pageUrl": getattr(ap, "url", ""), "receivedAt": _iso_now()}
                    # DOM
                    if args.capture_dom:
                        html = _safe_get_outer_html(ap)
                        if html is not None:
                            idxp = len(session.page_events) + 1
                            dp = session.dom_dir / f"P-{idxp:03}.html"
                            try:
                                dp.write_text(str(html), encoding="utf-8")
                                finalize_evt["domSnapshotPath"] = str(dp.relative_to(session.session_dir))
                            except Exception:
                                finalize_evt["domSnapshotError"] = "write-failed"
                    # Screenshot
                    if args.capture_screenshots:
                        idxp = len(session.page_events) + 1
                        sp = session.screenshot_dir / f"P-{idxp:03}.png"
                        spath = _safe_screenshot(ap, sp)
                        if spath:
                            finalize_evt["screenshotPath"] = str(Path(spath).relative_to(session.session_dir))
                        else:
                            finalize_evt["screenshotError"] = "shot-failed"
                    try:
                        session.add_page_event(finalize_evt)
                    except Exception:
                        pass
        except Exception:
            pass

        # Stop trace (with brief settle + retry) before closing
        if not args.no_trace and trace_path:
            try:
                # brief settle to allow late events to flush
                try:
                    time.sleep(0.2)
                except Exception:
                    pass
                attempts = 2
                while attempts > 0:
                    attempts -= 1
                    try:
                        if browser and browser.is_connected():
                            tracer.stop(path=str(trace_path))
                            break
                    except Exception as exc_inner:  # noqa: BLE001
                        if attempts == 0:
                            sys.stderr.write(f"[recorder] Failed to stop tracing (non-fatal): {exc_inner}\n")
                        try:
                            time.sleep(0.15)
                        except Exception:
                            pass
            except Exception as exc:  # noqa: BLE001
                # Non-fatal: transport can close before we stop tracing
                sys.stderr.write(f"[recorder] Trace stop error (ignored): {exc}\n")

        # Close will be handled in finally with guards; finalization moved to finally to allow HAR flush

    except Exception as exc:  # noqa: BLE001
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
        if session:
            try:
                meta_path = session.finalize(har_path=har_path, trace_path=trace_path)
                metadata_written = True
                print(f"[recorder] Recorded {len(session.actions)} actions.")
                print(f"[recorder] Metadata saved to {meta_path}")
                if har_path and Path(har_path).exists():
                    print(f"[recorder] HAR saved to {har_path}")
                if trace_path and trace_path.exists():
                    print(f"[recorder] Trace saved to {trace_path}")
                if args.capture_dom:
                    print(f"[recorder] DOM snapshots stored in {session.dom_dir}")
                if args.capture_screenshots:
                    print(f"[recorder] Screenshots stored in {session.screenshot_dir}")
            except Exception:
                pass


if __name__ == "__main__":
    try:
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    except (AttributeError, ValueError):
        pass
    main()
