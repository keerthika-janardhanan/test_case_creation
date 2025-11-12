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
from typing import Any, Dict, List, Optional, Union
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
from app.event_client import publish_recorder_event

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
    const cssPath = el => { const parts=[]; let n=el; while(n&&n.nodeType===1){ let sel=n.nodeName.toLowerCase(); if(n.id){parts.unshift(`${sel}#${n.id}`);break;} const p=n.parentNode; if(!p) break; const i=Array.from(p.children).indexOf(n)+1; parts.unshift(`${sel}:nth-child(${i})`); n=p;} return parts.join(' > '); };
    const roleOf = el => { if (!el) return ''; const r = el.getAttribute && el.getAttribute('role'); if (r) return r.toLowerCase(); const tag = (el.tagName||'').toLowerCase(); const type = (el.getAttribute && (el.getAttribute('type')||'').toLowerCase()) || '';
        if (tag === 'a' && el.getAttribute('href')) return 'link';
        if (tag === 'button' || (tag === 'input' && ['button','submit','reset'].includes(type))) return 'button';
        if (tag === 'img') return 'img';
        if (tag === 'input' && type === 'checkbox') return 'checkbox';
        if (tag === 'input' && (type === 'radio')) return 'radio';
        if (tag === 'input' || tag === 'textarea') return 'textbox';
        if (tag === 'select') return 'combobox';
        if (tag === 'li') return 'listitem';
        if (tag === 'ul' || tag === 'ol') return 'list';
        if (tag === 'option') return 'option';
        if (tag === 'table') return 'table';
        if (tag === 'tr') return 'row';
        if (tag === 'td' || tag === 'th') return 'cell';
        if (tag === 'nav') return 'navigation';
        return '';
    };
    const labelTexts = el => {
        const out = [];
        try { if (el && el.labels) { for (const l of Array.from(el.labels)) { const t=(l.innerText||l.textContent||'').trim(); if (t) out.push(t); } } } catch(_) {}
        try { const labelledby = el && el.getAttribute && el.getAttribute('aria-labelledby'); if (labelledby) { for (const id of labelledby.split(/\s+/)) { const n = document.getElementById(id); if (n) { const t=(n.innerText||n.textContent||'').trim(); if (t) out.push(t); } } } } catch(_) {}
        try { const parentLabel = el && el.closest && el.closest('label'); if (parentLabel) { const t=(parentLabel.innerText||parentLabel.textContent||'').trim(); if (t) out.push(t); } } catch(_) {}
        return out;
    };
    const accName = el => {
        if (!el) return '';
        const aria = el.getAttribute && el.getAttribute('aria-label'); if (aria) return aria.trim();
        const labs = labelTexts(el); if (labs.length) return labs.join(' ').trim().slice(0,150);
        const title = el.getAttribute && el.getAttribute('title'); if (title) return title.trim();
        const placeholder = el.getAttribute && el.getAttribute('placeholder'); if (placeholder) return placeholder.trim();
        const alt = el.getAttribute && el.getAttribute('alt'); if (alt) return alt.trim();
        const txt = (el.innerText || el.textContent || '').trim(); if (txt) return txt.slice(0,150);
        return '';
    };
    const ancestorChain = el => { const list=[]; let n=el; while(n && n.nodeType===1){ const p=n.parentElement; const idx = p ? (Array.from(p.children).indexOf(n)+1) : 1; list.unshift({ tag:(n.tagName||'').toLowerCase(), id:n.id||'', className:n.className||'', index:idx }); n=p; } return list; };
    const datasetObj = el => { const o={}; try { const d=el && el.dataset; if (d) { for (const k of Object.keys(d)) { o[k] = (''+d[k]).slice(0,120); } } } catch(_) {} return o; };
    const attrs = el => { const pick=['id','name','type','value','class','title','placeholder','alt','href','src','aria-label','aria-labelledby','aria-describedby']; const o={}; for (const a of pick){ try { const v=el.getAttribute && el.getAttribute(a); if (v!=null) o[a]=(''+v).slice(0,200); } catch(_){} } return o; };
    const styles = el => {
        try {
            const c = getComputedStyle(el);
            return {
                display: c.display,
                visibility: c.visibility,
                opacity: c.opacity,
                color: c.color,
                backgroundColor: c.backgroundColor,
                fontSize: c.fontSize,
                fontWeight: c.fontWeight,
                textTransform: c.textTransform,
                textAlign: c.textAlign,
            };
        } catch (_) {
            return {};
        }
    };
    const unique = sel => { try { return !!sel && document.querySelectorAll(sel).length === 1; } catch(_) { return false; } };
    const cssId = el => el.id ? `#${CSS.escape(el.id)}` : '';
    const cssData = el => { const keys=['testid','test','qa']; for (const k of keys){ const d=el.dataset && el.dataset[k]; if (d){ const s=`[data-${k}="${CSS.escape(d)}"]`; if (unique(s)) return s; } } return ''; };
    const nameAttrSel = el => { const n=el.getAttribute && el.getAttribute('name'); if (n){ const s=`[name="${CSS.escape(n)}"]`; if (unique(s)) return s; } return ''; };
    const makeStableSelector = el => {
        // Prefer id / data-* / [name]
        const byId = cssId(el); if (byId && unique(byId)) return byId;
        const byData = cssData(el); if (byData) return byData;
        const byName = nameAttrSel(el); if (byName) return byName;
        // Prefer Playwright-style role+name if available
        const r = roleOf(el); const n = accName(el);
        if (r && n) return `getByRole(\"${r}\", { name: \"${n.replace(/\"/g,'\\\"')}\" })`;
        // Prefer label
        const labs = labelTexts(el); if (labs && labs.length){ const l=labs[0].replace(/\"/g,'\\\"'); return `getByLabel(\"${l}\")`; }
        // Fallback to text
        const t = (el.innerText||el.textContent||'').trim(); if (t) return `getByText(\"${t.slice(0,80).replace(/\"/g,'\\\"')}\")`;
        // Fallback to CSS path then XPath
        const cssp = cssPath(el); if (cssp) return cssp;
        return xp(el);
    };
    const relations = el => {
        const parentEl = el && el.parentElement ? el.parentElement : null;
        const parent = parentEl
            ? {
                  tag: (parentEl.tagName || "").toLowerCase(),
                  id: parentEl.id || "",
                  className: parentEl.className || "",
              }
            : null;
        const parentAttributes = parentEl ? attrs(parentEl) : {};
        const prev = el && el.previousElementSibling
            ? {
                  tag: (el.previousElementSibling.tagName || "").toLowerCase(),
                  text: (el.previousElementSibling.innerText || "").trim().slice(0, 120),
              }
            : null;
        const next = el && el.nextElementSibling
            ? {
                  tag: (el.nextElementSibling.tagName || "").toLowerCase(),
                  text: (el.nextElementSibling.innerText || "").trim().slice(0, 120),
              }
            : null;
        const siblingIndex = parentEl ? Array.from(parentEl.children).indexOf(el) + 1 : 1;
        const siblings = [];
        if (parentEl) {
            const kids = Array.from(parentEl.children);
            for (const sib of kids) {
                if (sib === el) continue;
                if (siblings.length >= 6) break;
                siblings.push({
                    tag: (sib.tagName || "").toLowerCase(),
                    text: (sib.innerText || "").trim().slice(0, 120),
                    id: sib.id || "",
                    className: sib.className || "",
                });
            }
        }
        return {
            parent,
            parentAttributes,
            previousSibling: prev,
            nextSibling: next,
            siblingIndex,
            siblings,
        };
    };

    const HEADING_SELECTOR = "h1,h2,h3,h4,h5,h6,[role='heading']";
    const headingLevel = h => {
        try {
            const tag = (h.tagName || '').toLowerCase();
            if (/^h[1-6]$/.test(tag)) return tag;
            const aria = h.getAttribute && (h.getAttribute('aria-level') || '');
            if (aria) return `h${aria}`;
            const role = h.getAttribute && (h.getAttribute('role') || '');
            if (role === 'heading') return 'heading';
        } catch(_) {}
        return '';
    };
    const nearestHeading = el => {
        let current = el;
        while (current && current !== document.body) {
            let walker = current;
            while (walker) {
                walker = walker.previousElementSibling;
                if (walker && walker.matches && walker.matches(HEADING_SELECTOR)) {
                    const text = (walker.innerText || walker.textContent || "").trim();
                    if (text) {
                        return { level: headingLevel(walker), text: text.slice(0, 180), id: walker.id || "" };
                    }
                }
            }
            current = current.parentElement;
        }
        return null;
    };

    const collectHeadings = () => {
        try {
            return Array.from(document.querySelectorAll(HEADING_SELECTOR)).map(h => ({
                level: headingLevel(h),
                text: (h.innerText || h.textContent || "").trim().slice(0, 180),
                id: h.id || "",
                xpath: xp(h),
            }));
        } catch (_) {
            return [];
        }
    };
    const computeMainHeading = (heads) => {
        try {
            if (!heads || !heads.length) return '';
            const byText = heads.filter(h => (h.text||'').trim());
            const firstH1 = byText.find(h => (h.level||'').toLowerCase() === 'h1');
            if (firstH1) return firstH1.text;
            const ariaLevel1 = byText.find(h => (h.level||'').toLowerCase() === 'h1' || (h.level||'').toLowerCase() === 'h1');
            if (ariaLevel1) return ariaLevel1.text;
            return byText[0] ? byText[0].text : '';
        } catch(_) { return ''; }
    };
    const snap = raw => {
        const el = norm(raw); if (!el) return null; let r=null; try{ r=el.getBoundingClientRect(); }catch(e){}
        const role = roleOf(el); const name = accName(el);
        const labels = labelTexts(el);
        const cssSnapshot = styles(el);
        const element = {
            tag: (el.tagName||'').toLowerCase(),
            id: el.id||'',
            className: el.className||'',
            role: role || '',
            name: name || '',
            ariaLabel: (el.getAttribute && el.getAttribute('aria-label')) || '',
            title: (el.getAttribute && el.getAttribute('title')) || '',
            placeholder: (el.getAttribute && el.getAttribute('placeholder')) || '',
            text: (el && el.textContent ? el.textContent.trim().slice(0,150) : ''),
            labels,
            attributes: attrs(el),
            dataset: datasetObj(el),
            xpath: xp(el),
            cssPath: cssPath(el),
            ancestors: ancestorChain(el),
            relations: relations(el),
            styles: cssSnapshot,
            cssProperties: cssSnapshot,
            nearestHeading: nearestHeading(el),
            rect: r?{x:r.x,y:r.y,width:r.width,height:r.height}:null,
        };
        element.stableSelector = makeStableSelector(el);
        element.playwright = { byRole: (role && name) ? { role, name } : null, byLabel: (labels[0]||'') || null, byText: ((el.innerText||el.textContent||'').trim().slice(0,80)) || null };
        return element;
    };
    const send = (action, target, extra) => {
        const element = snap(target);
        const payload = { action, pageUrl: location.href, pageTitle: document.title, timestamp: Date.now(), element, extra: extra||{} };
        try {
            console.debug('[recorder] action', action, element && element.tag || '', location.href);
            // Emit a single-string JSON line for robust fallback capture
            console.debug('[recorder-json] ' + JSON.stringify(payload));
        } catch(_) {}
        sendCap(payload);
    };
    // Event capture (reduced noise)
    document.addEventListener('click', e => send('click', targetOf(e), {button:e.button}), true);
    document.addEventListener('dblclick', e => send('dblclick', targetOf(e), {button:e.button}), true);
    document.addEventListener('contextmenu', e => send('contextmenu', targetOf(e), {button:e.button}), true);
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
    const sendCtx = (trigger) => {
        const payload = {
            pageUrl: location.href,
            title: document.title,
            timestamp: Date.now(),
            trigger,
            headings: collectHeadings(),
            mainHeading: computeMainHeading(collectHeadings()),
            viewport: { width: window.innerWidth, height: window.innerHeight },
        };
        sendCtxI(payload);
    };
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


def _mask_sensitive(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = str(value)
    lowered = text.lower()
    sensitive_tokens = ("password", "secret", "token", "passcode", "otp", "ssn", "credit")
    if any(token in lowered for token in sensitive_tokens):
        return "********"
    if "@" in text and " " not in text:
        return "<email>"
    if len(text) > 120:
        return f"{text[:12]}...{text[-6:]}"
    return text


def _timestamp_to_iso(value: Optional[Union[int, float, str]]) -> Optional[str]:
    if value is None:
        return None
    try:
        if isinstance(value, str):
            if value.isdigit():
                value = int(value)
            else:
                # Assume already ISO or parseable string
                return value
        if isinstance(value, (int, float)):
            seconds = float(value)
            if seconds > 1_000_000_000_000:  # milliseconds
                seconds /= 1000.0
            return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat()
    except Exception:
        return None
    return None


class RecorderSession:
    def __init__(self, session_dir: Path, capture_dom: bool, capture_screenshots: bool, options: Dict[str, Any]) -> None:
        self.session_dir = session_dir
        self.capture_dom = capture_dom
        self.capture_screenshots = capture_screenshots
        self.options = dict(options)
        self.metadata_path = self.session_dir / "metadata.json"
        self.dom_dir = self.session_dir / "dom"
        self.screenshot_dir = self.session_dir / "screenshots"
        if self.capture_dom:
            self.dom_dir.mkdir(parents=True, exist_ok=True)
        if self.capture_screenshots:
            self.screenshot_dir.mkdir(parents=True, exist_ok=True)

        self.started_at = _iso_now()
        self.ended_at: Optional[str] = None
        self.actions: List[Dict[str, Any]] = []
        self.page_events: List[Dict[str, Any]] = []
        self._artifacts: Dict[str, Optional[str]] = {"har": None, "trace": None}
        self._warnings: List[str] = []

        self.flow_name: str = (self.options.get("flowName") or "").strip() or self.session_dir.name
        self.environment: Dict[str, Any] = {
            "browser": self.options.get("browser"),
            "headless": self.options.get("headless"),
            "userAgent": self.options.get("userAgent"),
            "proxy": self.options.get("proxy"),
        }
        self.environment = {k: v for k, v in self.environment.items() if v not in (None, "", False)}

        self._pages_by_key: Dict[str, Dict[str, Any]] = {}
        self._page_order: List[str] = []
        self._runtime_lookup: Dict[int, str] = {}
        self._page_counter = 0

        self.metadata_version = "2025.10"
        self._persist()

    # ---- Page bookkeeping -------------------------------------------------
    def _derive_page_key(self, runtime_page: Optional[Page], page_url: Optional[str]) -> str:
        if runtime_page is not None:
            rid = id(runtime_page)
            existing = self._runtime_lookup.get(rid)
            if existing:
                return existing
            # Maybe the page was recorded previously but runtime lookup cleared
            for key, entry in self._pages_by_key.items():
                if entry.get("runtimeId") == rid:
                    self._runtime_lookup[rid] = key
                    return key
            key = f"runtime:{rid}"
            self._runtime_lookup[rid] = key
            return key

        if page_url:
            for key in self._page_order:
                entry = self._pages_by_key.get(key, {})
                if entry.get("pageUrl") == page_url:
                    return key
            return f"url:{page_url}"

        return f"synthetic:{len(self._page_order) + 1}"

    def _ensure_page_entry(
        self,
        runtime_page: Optional[Page],
        page_url: Optional[str],
        page_title: Optional[str],
        headings: Optional[List[Dict[str, Any]]] = None,
        viewport: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        key = self._derive_page_key(runtime_page, page_url)
        entry = self._pages_by_key.get(key)
        if not entry:
            self._page_counter += 1
            entry = {
                "pageId": f"page-{self._page_counter}",
                "pageRef": key,
                "pageUrl": page_url,
                "pageTitle": page_title,
                "headings": list(headings or []),
                "mainHeading": None,
                "viewport": dict(viewport or {}),
                "actions": [],
                "artifacts": {
                    "domSnapshots": [],
                    "screenshots": [],
                },
                "runtimeId": id(runtime_page) if runtime_page is not None else None,
            }
            self._pages_by_key[key] = entry
            self._page_order.append(key)
            if runtime_page is not None:
                self._runtime_lookup[id(runtime_page)] = key
        else:
            if page_url:
                entry["pageUrl"] = page_url
            if page_title:
                entry["pageTitle"] = page_title
            if headings:
                entry["headings"] = list(headings)
            if viewport:
                entry["viewport"] = dict(viewport)
            if runtime_page is not None and not entry.get("runtimeId"):
                entry["runtimeId"] = id(runtime_page)
                self._runtime_lookup[id(runtime_page)] = key
        if viewport and "viewport" not in self.environment:
            self.environment["viewport"] = dict(viewport)
        return entry

    # ---- Serialization helpers -------------------------------------------
    def _build_selector_strategies(self, element: Dict[str, Any]) -> Dict[str, Optional[str]]:
        strategies: Dict[str, Optional[str]] = {}
        stable = element.get("stableSelector")
        if stable:
            strategies["playwright"] = stable
        css_path = element.get("cssPath")
        if css_path:
            strategies["css"] = css_path
        xpath = element.get("xpath")
        if xpath:
            strategies["xpath"] = xpath
        playwright_meta = element.get("playwright") or {}
        by_role = playwright_meta.get("byRole")
        if isinstance(by_role, dict) and by_role.get("role") and by_role.get("name"):
            strategies["aria"] = f"getByRole('{by_role['role']}', {{ name: '{by_role['name']}' }})"
        elif playwright_meta.get("byLabel"):
            strategies["aria"] = f"getByLabel('{playwright_meta['byLabel']}')"
        elif playwright_meta.get("byText"):
            strategies["text"] = f"getByText('{playwright_meta['byText']}')"
        return strategies

    def _derive_input_summary(self, action_type: str, extra: Dict[str, Any], element: Dict[str, Any]) -> Optional[str]:
        if action_type in ("input", "change", "fill", "type"):
            raw = extra.get("value")
            masked = extra.get("valueMasked")
            if masked and masked is not True:
                return f"Value: {masked}"
            if raw:
                masked_val = _mask_sensitive(raw)
                return f"Value: {masked_val}"
        if action_type in ("press", "keyrelease"):
            key = extra.get("key")
            if key:
                return f"Key: {key}"
        if action_type == "click":
            button = extra.get("button")
            if button:
                return f"Button: {button}"
        if element.get("nearestHeading"):
            heading = element["nearestHeading"]
            if isinstance(heading, dict) and heading.get("text"):
                return f"Section: {heading['text']}"
        return None

    def _normalize_element(self, element: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:
        norm = dict(element or {})
        if "labels" not in norm:
            norm["labels"] = extra.get("labels") or []
        if "cssProperties" not in norm and "styles" in norm:
            norm["cssProperties"] = dict(norm.get("styles", {}))
        if "styles" not in norm and "cssProperties" in norm:
            norm["styles"] = dict(norm.get("cssProperties", {}))
        if "relations" in norm:
            rel = norm["relations"]
            if isinstance(rel, dict):
                rel.setdefault("siblings", [])
        if "nearestHeading" in norm and isinstance(norm["nearestHeading"], dict):
            norm["nearestHeading"] = {
                "level": norm["nearestHeading"].get("level"),
                "text": norm["nearestHeading"].get("text"),
                "id": norm["nearestHeading"].get("id"),
            }
        value_from_extra = extra.get("value")
        if value_from_extra and "value" not in norm:
            norm["value"] = value_from_extra
        if extra.get("valueMasked") and "valueMasked" not in norm:
            norm["valueMasked"] = extra.get("valueMasked")
        if any(norm.get(key) for key in ("ariaLabel", "title", "placeholder", "text")):
            # ensure trimmed strings
            for key in ("ariaLabel", "title", "placeholder", "text"):
                if key in norm and isinstance(norm[key], str):
                    norm[key] = norm[key].strip()
        return norm

    def _serialize_pages(self) -> List[Dict[str, Any]]:
        pages: List[Dict[str, Any]] = []
        for key in self._page_order:
            entry = self._pages_by_key.get(key)
            if not entry:
                continue
            page = {
                "pageId": entry.get("pageId"),
                "pageRef": entry.get("pageRef"),
                "pageUrl": entry.get("pageUrl"),
                "pageTitle": entry.get("pageTitle"),
                "headings": entry.get("headings", []),
                "mainHeading": entry.get("mainHeading"),
                "viewport": entry.get("viewport") or {},
                "artifacts": entry.get("artifacts", {}),
                "actions": entry.get("actions", []),
            }
            pages.append(page)
        return pages

    # ---- Public API ------------------------------------------------------
    def add_page_event(self, payload: Dict[str, Any], runtime_page: Optional[Page] = None) -> None:
        data = dict(payload or {})
        data["receivedAt"] = _iso_now()

        headings = data.get("headings") if isinstance(data.get("headings"), list) else None
        main_heading = data.get("mainHeading") if isinstance(data.get("mainHeading"), (str, type(None))) else None
        viewport = data.get("viewport") if isinstance(data.get("viewport"), dict) else None
        page_url = data.get("pageUrl") or data.get("url")
        page_title = data.get("title")

        entry = self._ensure_page_entry(runtime_page, page_url, page_title, headings, viewport)
        entry.setdefault("lastContextReceivedAt", data["receivedAt"])
        entry.setdefault("lastTrigger", data.get("trigger"))
        if main_heading is not None:
            entry["mainHeading"] = main_heading

        artifacts = entry.setdefault("artifacts", {"domSnapshots": [], "screenshots": []})
        dom_path = data.get("domSnapshotPath")
        if dom_path:
            artifacts.setdefault("domSnapshots", []).append(dom_path)
        screenshot_path = data.get("screenshotPath")
        if screenshot_path:
            artifacts.setdefault("screenshots", []).append(screenshot_path)

        self.page_events.append(data)
        self._persist()

    def add_action(self, payload: Dict[str, Any], runtime_page: Optional[Page] = None) -> None:
        data = dict(payload or {})
        received_at = _iso_now()
        data["receivedAt"] = received_at

        extra = data.get("extra")
        if not isinstance(extra, dict):
            extra = {}
        # Mask any sensitive artifacts
        if "value" in extra:
            extra["valueMasked"] = extra.get("valueMasked") or _mask_sensitive(extra["value"])
        data["extra"] = extra

        # If this came from the console fallback, don't discard it; mark as degraded so
        # downstream can still load steps even when bindings are blocked (e.g., CSP).
        # Keep a single warning, but persist the action.
        if extra.get("fromConsole"):
            note = "Using degraded console fallback for action due to missing binding context."
            if note not in self._warnings:
                self._warnings.append(note)
                # don't early-return; continue to persist a minimal action record

        page_url = data.get("pageUrl")
        page_title = data.get("pageTitle")
        entry = self._ensure_page_entry(runtime_page, page_url, page_title)

        action_id = data.get("actionId")
        if not action_id:
            action_id = f"A-{len(self.actions) + 1:03}"
            data["actionId"] = action_id

        raw_ts = data.get("timestamp")
        timestamp_iso = _timestamp_to_iso(raw_ts) or received_at
        data["timestampEpochMs"] = raw_ts
        data["timestamp"] = timestamp_iso

        action_type = (data.get("action") or data.get("type") or "interaction").lower()
        data["action"] = action_type
        data["type"] = action_type
        data["pageUrl"] = entry.get("pageUrl")
        data["pageTitle"] = entry.get("pageTitle")
        data["pageId"] = entry.get("pageId")

        # Attach element details (may be minimal for console-fallback)
        element_data = self._normalize_element(data.get("element") or {}, extra)
        data["element"] = element_data
        data["selectorStrategies"] = self._build_selector_strategies(element_data)
        data["inputSummary"] = self._derive_input_summary(action_type, extra, element_data)
        data["artifacts"] = {
            "screenshot": data.get("screenshotPath"),
            "domSnapshot": data.get("domSnapshotPath"),
        }
        if extra.get("fromConsole"):
            data["degraded"] = True
            data.setdefault("notes", []).append("Recorded via console debug fallback; selectors may be incomplete.")

        entry["actions"].append(data)
        self.actions.append(data)
        self._persist()

    def _refresh_flow_name(self) -> None:
        label_path = self.session_dir / "flow_name.txt"
        if label_path.exists():
            try:
                value = label_path.read_text(encoding="utf-8").strip()
                if value:
                    self.flow_name = value
            except Exception:
                pass

    def _persist(self) -> None:
        summary = {
            "metadataVersion": self.metadata_version,
            "flowId": self.session_dir.name,
            "flowName": self.flow_name,
            "runTimestamp": self.started_at,
            "environment": self.environment,
            "pages": self._serialize_pages(),
            "warnings": list(self._warnings),
            "artifacts": self._artifacts,
            # Legacy compatibility fields
            "session": {
                "id": self.session_dir.name,
                "startedAt": self.started_at,
            },
            "options": self.options,
            "pageContextEvents": self.page_events,
            "actions": self.actions,
        }
        if self.ended_at:
            summary["session"]["endedAt"] = self.ended_at
        try:
            self.metadata_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        except Exception:
            pass

    def finalize(self, har_path: Optional[Path], trace_path: Optional[Path]) -> Path:
        self._refresh_flow_name()
        self.ended_at = _iso_now()
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
    bypass_csp: bool = False,
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
    if bypass_csp:
        ctx_kwargs["bypass_csp"] = True
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
    parser.add_argument("--bypass-csp", action="store_true")
    parser.add_argument("--flow-name", default=None)

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
    publish_recorder_event(
        session_name,
        "Recorder launcher initialised",
        url=args.url,
        browser=args.browser,
        timeout=args.timeout,
    )

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
            bypass_csp=args.bypass_csp,
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
                "bypassCsp": args.bypass_csp,
                "flowName": args.flow_name,
            },
        )

        # Queues to avoid Playwright API calls inside binding callbacks (deadlock risk)
        pending_actions = deque()
        pending_ctx = deque()
        q_lock = threading.Lock()
        # Track recent binding-delivered actions to suppress console fallbacks
        last_binding_action_at: float = 0.0
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
                # binding delivered; note the time
                try:
                    nonlocal last_binding_action_at
                    last_binding_action_at = time.time()
                except Exception:
                    pass

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
                # Fallback: only consider our debug logs and only if no recent binding events
                if (
                    session
                    and isinstance(text, str)
                    and msg.type == "debug"
                ):
                    # If bindings have been active within the last 1s, skip fallback to avoid duplicates
                    now = time.time()
                    try:
                        nonlocal last_binding_action_at
                        if last_binding_action_at and (now - last_binding_action_at) < 1.0:
                            return
                    except Exception:
                        pass
                    # Prefer JSON payloads
                    if text.startswith("[recorder-json]"):
                        try:
                            jtxt = text[len("[recorder-json]"):].strip()
                            payload = json.loads(jtxt)
                            if isinstance(payload, dict):
                                ex = payload.get("extra") or {}
                                ex["fromConsole"] = True
                                payload["extra"] = ex
                                session.add_action(payload, runtime_page=None)
                                return
                        except Exception:
                            pass
                    # Legacy simple fallback: "[recorder] action <action> <tag> <url>"
                    if text.startswith("[recorder] action"):
                        parts = text.split()
                        if len(parts) >= 5:
                            act = parts[2]
                            tag = parts[3]
                            url = parts[4]
                            fallback = {"action": act, "pageUrl": url, "element": {"tag": tag}, "extra": {"fromConsole": True}}
                            try:
                                session.add_action(fallback, runtime_page=None)
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
                        evt.pop("__frame", None)
                        page_ref = evt.pop("__page", None)
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
                        session.add_page_event(evt, runtime_page=page_ref)

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
                        session.add_action(act, runtime_page=page_ref)
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
                    evt.pop("__frame", None)
                    page_ref = evt.pop("__page", None)
                    try:
                        session.add_page_event(evt, runtime_page=page_ref)
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
                    act.pop("__frame", None)
                    page_ref = act.pop("__page", None)
                    try:
                        session.add_action(act, runtime_page=page_ref)
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
                        session.add_page_event(finalize_evt, runtime_page=ap)
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
                publish_recorder_event(
                    session_name,
                    "Recorder session artefacts saved",
                    actions=len(session.actions),
                    metadata_path=str(meta_path),
                )
            except Exception:
                publish_recorder_event(
                    session_name,
                    "Recorder finalization failed",
                    level="error",
                )
                pass
        else:
            publish_recorder_event(session_name, "Recorder session aborted", level="warning")


if __name__ == "__main__":
    try:
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    except (AttributeError, ValueError):
        pass
    main()
