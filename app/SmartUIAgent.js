/**
 * SmartUIAgent – Agentic UI Action Recorder (Vanilla JS + optional html2canvas)
 * --------------------------------------------------------------------------
 * Drop this script into your web application (after html2canvas if you want screenshots)
 * and instantiate via:
 *
 *   const agent = new SmartUIAgent({ enableScreenshots: true });
 *   agent.start();
 *
 * The agent observes user activity, decides what to record, explains why,
 * and offers a lightweight conversational console plus export utilities.
 */

(() => {
  /* ---------------------------------------------------------------------- */
  /* Utilities                                                              */
  /* ---------------------------------------------------------------------- */

  const truncate = (text, max = 160) =>
    typeof text === "string" && text.length > max ? `${text.slice(0, max - 3)}…` : text;

  const stableNow = () => (performance && performance.now ? performance.now() : Date.now());

  const safeStringify = (obj) => {
    try {
      return JSON.stringify(obj);
    } catch {
      return "";
    }
  };

  const generateCSSSelector = (el) => {
    if (!el || el.nodeType !== Node.ELEMENT_NODE) return "";
    const path = [];
    let node = el;
    while (node && node.nodeType === Node.ELEMENT_NODE) {
      const name = node.nodeName.toLowerCase();
      if (node.id) {
        path.unshift(`#${node.id}`);
        break;
      }
      const siblings = Array.from(node.parentNode ? node.parentNode.children : []);
      const sameTagSiblings = siblings.filter((sib) => sib.nodeName === node.nodeName);
      if (sameTagSiblings.length > 1) {
        const index = sameTagSiblings.indexOf(node) + 1;
        path.unshift(`${name}:nth-of-type(${index})`);
      } else {
        path.unshift(name);
      }
      node = node.parentNode;
    }
    return path.join(" > ");
  };

  const generateXPath = (el) => {
    if (!el || el.nodeType !== Node.ELEMENT_NODE) return "";
    if (el.id) {
      return `//*[@id="${el.id}"]`;
    }
    const parts = [];
    let node = el;
    while (node && node.nodeType === Node.ELEMENT_NODE) {
      let index = 1;
      let sibling = node.previousSibling;
      while (sibling) {
        if (sibling.nodeType === Node.DOCUMENT_TYPE_NODE) {
          sibling = sibling.previousSibling;
          continue;
        }
        if (sibling.nodeName === node.nodeName) index += 1;
        sibling = sibling.previousSibling;
      }
      const tagName = node.nodeName.toLowerCase();
      const nth = index > 1 ? `[${index}]` : "";
      parts.unshift(`${tagName}${nth}`);
      node = node.parentNode;
    }
    return `/${parts.join("/")}`;
  };

  const captureScreenshot = async ({ element, fullPage, quality = 0.6, scale = 1 }) => {
    if (typeof html2canvas !== "function") {
      return { error: "html2canvas not available" };
    }
    const target = fullPage ? document.body : element;
    if (!target) return { error: "No target for screenshot" };
    const canvas = await html2canvas(target, { scale, logging: false, useCORS: true });
    return { dataUrl: canvas.toDataURL("image/jpeg", quality) };
  };

  /* ---------------------------------------------------------------------- */
  /* Core Data Structures                                                   */
  /* ---------------------------------------------------------------------- */

  class SessionContext {
    constructor() {
      this.events = [];
      this.startedAt = new Date().toISOString();
      this.lastEventTime = stableNow();
      this.recentElements = new Map();
      this.activeIntent = null;
      this.domMutations = 0;
      this.viewMetrics = {
        viewport: { width: window.innerWidth, height: window.innerHeight },
        devicePixelRatio: window.devicePixelRatio || 1,
        url: location.href,
        referrer: document.referrer,
        userAgent: navigator.userAgent,
      };
    }

    updateWithEvent(record) {
      this.events.push(record);
      this.lastEventTime = stableNow();
      const key = record.meta.selector || record.meta.xpath;
      if (key) {
        const hits = this.recentElements.get(key) || { count: 0, lastTimestamp: 0 };
        hits.count += 1;
        hits.lastTimestamp = record.timestamp;
        this.recentElements.set(key, hits);
      }
      if (!this.activeIntent && record.meta.intent) {
        this.activeIntent = record.meta.intent;
      }
    }

    registerDomMutation() {
      this.domMutations += 1;
    }

    toJSON() {
      return {
        startedAt: this.startedAt,
        events: this.events,
        domMutations: this.domMutations,
        activeIntent: this.activeIntent,
        environment: this.viewMetrics,
      };
    }
  }

  class DecisionEngine {
    constructor(config = {}) {
      this.config = Object.assign(
        {
          baseWeights: {
            click: 2,
            input: 2,
            change: 2,
            submit: 3,
            hover: 0.5,
            focus: 1.5,
            blur: 1,
          },
          elementWeights: {
            BUTTON: 3,
            A: 2.5,
            INPUT: 3,
            SELECT: 3,
            TEXTAREA: 3,
            FORM: 4,
            LABEL: 1.5,
            TABLE: 1.5,
            DIALOG: 3,
          },
          contextComplexityThreshold: 8,
          anomalyThreshold: 4,
          density: "adaptive",
        },
        config
      );
      this.recentDecisions = [];
    }

    evaluate(payload, session) {
      const score = this._score(payload, session);
      const priority = this._priority(payload, score);
      const anomaly = this._detectAnomaly(payload, session);
      const shouldRecord = this._shouldRecord(score, priority, anomaly, session);
      const reason = this._explainDecision(score, priority, anomaly, payload);
      this._rememberDecision({ time: Date.now(), score, priority, anomaly, payload, reason, kept: shouldRecord });
      return { shouldRecord, score, priority, anomaly, reason };
    }

    _score(payload, session) {
      const weights = this.config.baseWeights;
      let score = weights[payload.eventType] || 1;

      const tagWeight = this.config.elementWeights[payload.element.tagName] || 1;
      score += tagWeight;

      if (payload.element.role) score += 1;
      if (payload.element.dataset && payload.element.dataset.testid) score += 2;
      if (payload.element.attributes.type === "submit") score += 2;
      if (payload.element.attributes["aria-label"]) score += 1.5;
      if (payload.element.textLength > 0 && payload.element.textLength < 120) score += 0.5;
      if (payload.meta.isPrimaryAction) score += 2;

      if (payload.eventType === "input" || payload.eventType === "change") {
        const value = payload.element.value || "";
        if (value && value.length > 0) score += Math.min(4, value.length / 8);
      }

      if (payload.meta.path.includes("checkout") || /login|auth|payment/i.test(payload.meta.selector)) {
        score += 2.5;
      }

      const mutations = session.domMutations;
      if (mutations > 10) score += 1;
      if (mutations > 30) score += 1;

      const recency = session.recentElements.get(payload.meta.selector);
      if (recency && recency.count > 3) score -= Math.min(3, recency.count - 2);

      return score;
    }

    _priority(payload, score) {
      if (score >= 9) return "critical";
      if (score >= 6) return "high";
      if (score >= 4) return "medium";
      return "low";
    }

    _detectAnomaly(payload, session) {
      const recency = session.recentElements.get(payload.meta.selector);
      if (recency && recency.count >= this.config.anomalyThreshold) {
        return `Repeated interaction on ${payload.meta.selector} (${recency.count} times). Possible usability issue.`;
      }
      if (payload.eventType === "submit" && payload.meta.formErrors && payload.meta.formErrors.length) {
        return `Form submission returned errors: ${payload.meta.formErrors.join(", ")}`;
      }
      return null;
    }

    _shouldRecord(score, priority, anomaly, session) {
      if (anomaly) return true;
      if (priority === "critical" || priority === "high") return true;
      if (this.config.density === "dense") return score >= 2;
      if (this.config.density === "sparse") return score >= 7;

      const baseline = session.events.length < this.config.contextComplexityThreshold ? 3 : 5;
      return score >= baseline;
    }

    _explainDecision(score, priority, anomaly, payload) {
      if (anomaly) return `Recorded due to anomaly: ${anomaly}`;
      return `Recorded ${payload.eventType} on ${payload.element.tagName.toLowerCase()} with score ${score.toFixed(
        1
      )} (${priority} priority) based on role, context, and intent signals.`;
    }

    _rememberDecision(decision) {
      this.recentDecisions.push(decision);
      if (this.recentDecisions.length > 200) this.recentDecisions.shift();
    }
  }

  class MetadataCollector {
    constructor(config = {}) {
      this.config = Object.assign(
        {
          enableScreenshots: true,
          screenshotFullPage: false,
          screenshotScale: 0.5,
          captureStyles: true,
          captureDomContextDepth: 3,
          aiAnnotations: true,
        },
        config
      );
    }

    async collect(payload) {
      const { element, meta } = payload;
      const target = element.reference;
      const computed = target ? window.getComputedStyle(target) : null;

      const domMeta = {
        tagName: element.tagName,
        role: element.role,
        attributes: element.attributes,
        dataset: element.dataset,
        text: truncate(element.textContent, 200),
        value: truncate(element.value, 120),
        selector: meta.selector,
        xpath: meta.xpath,
        path: meta.path,
        position: meta.position,
        boundingRect: meta.boundingRect,
        styles: computed
          ? {
              display: computed.display,
              visibility: computed.visibility,
              opacity: computed.opacity,
              color: computed.color,
              background: computed.background,
              fontSize: computed.fontSize,
              fontWeight: computed.fontWeight,
            }
          : undefined,
        relations: this._extractRelations(target),
      };

      const annotations = this.config.aiAnnotations ? this._annotate(element, meta) : {};

      let screenshot = null;
      if (this.config.enableScreenshots && target) {
        try {
          screenshot = await captureScreenshot({
            element: target,
            fullPage: this.config.screenshotFullPage,
            scale: this.config.screenshotScale,
          });
        } catch (err) {
          screenshot = { error: err?.message || "Unknown screenshot error" };
        }
      }

      return {
        dom: domMeta,
        context: {
          url: location.href,
          title: document.title,
          viewport: { width: window.innerWidth, height: window.innerHeight, devicePixelRatio: window.devicePixelRatio },
          timestamp: new Date().toISOString(),
          scroll: { x: window.scrollX, y: window.scrollY },
          performance: this._capturePerformance(),
          annotations,
        },
        media: screenshot,
      };
    }

    _extractRelations(node) {
      if (!node || !node.parentElement) return {};
      const parent = node.parentElement;
      const siblings = Array.from(parent.children).map((child) => child.tagName.toLowerCase());
      const children = Array.from(node.children)
        .slice(0, 8)
        .map((child) => child.tagName.toLowerCase());
      return {
        parent: parent.tagName.toLowerCase(),
        siblings: truncate(siblings.join(", "), 120),
        children,
        ordinalPosition: siblings.indexOf(node.tagName.toLowerCase()) + 1,
      };
    }

    _capturePerformance() {
      if (!performance || typeof performance.getEntriesByType !== "function") return null;
      const nav = performance.getEntriesByType("navigation");
      return nav && nav.length
        ? {
            type: nav[0].type,
            domInteractive: nav[0].domInteractive,
            domContentLoaded: nav[0].domContentLoadedEventEnd,
            loadEventEnd: nav[0].loadEventEnd,
          }
        : null;
    }

    _annotate(element, meta) {
      const annotations = {};
      if (/password|passcode|otp/i.test(meta.selector)) {
        annotations.intent = "credential-entry";
        annotations.sensitivity = "high";
      } else if (/checkout|payment|invoice|order/i.test(meta.path)) {
        annotations.intent = "transaction";
        annotations.priority = "business-critical";
      } else if (element.tagName === "FORM") {
        annotations.intent = "form-submission";
      } else if (element.tagName === "BUTTON" && /submit|save|confirm/i.test(element.textContent || "")) {
        annotations.intent = "action-confirmation";
      }

      const importance =
        (element.attributes["aria-label"] ? 1 : 0) +
        (element.dataset && Object.keys(element.dataset).length ? 1 : 0) +
        (element.role ? 1 : 0);

      annotations.visualImportance = importance >= 2 ? "high" : importance > 0 ? "medium" : "low";
      annotations.userIntent = this._predictIntent(element);
      return annotations;
    }

    _predictIntent(element) {
      if (!element || !element.tagName) return "unknown";
      const tag = element.tagName;
      const text = (element.textContent || "").toLowerCase();
      if (tag === "BUTTON" && /next|continue|proceed/.test(text)) return "progress";
      if (tag === "BUTTON" && /submit|save/.test(text)) return "completion";
      if (tag === "INPUT" && (element.attributes.type === "email" || /email/.test(text))) return "identity-entry";
      if (tag === "A" && /logout|sign out/.test(text)) return "session-end";
      return "interaction";
    }
  }

  class StorageManager {
    constructor(agent) {
      this.agent = agent;
    }

    exportSession() {
      const payload = this.agent.session.toJSON();
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `smartui-session-${Date.now()}.json`;
      link.click();
      URL.revokeObjectURL(url);
    }

    exportReport() {
      const events = this.agent.session.events;
      const lines = events.map(
        (ev, idx) =>
          `#${idx + 1} • ${ev.eventType.toUpperCase()} • ${ev.meta.selector}\nReason: ${ev.reason}\nAnnotations: ${safeStringify(
            ev.metadata.context.annotations
          )}\n---`
      );
      const blob = new Blob([lines.join("\n")], { type: "text/plain" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `smartui-report-${Date.now()}.txt`;
      link.click();
      URL.revokeObjectURL(url);
    }

    generateTestCaseDraft() {
      const events = this.agent.session.events.slice(0, 20);
      const steps = events
        .map(
          (ev, idx) =>
            `${idx + 1}. ${ev.eventType} ${ev.metadata.dom.tagName.toLowerCase()} (${ev.metadata.dom.selector}) – ${ev.reason}`
        )
        .join("\n");
      return `Test Case Draft: ${document.title}\nScenario: ${this.agent.session.activeIntent || "Captured flow"}\nSteps:\n${steps}`;
    }
  }

  class ConversationInterface {
    constructor(agent, config = {}) {
      this.agent = agent;
      this.config = Object.assign(
        {
          position: "bottom-right",
          collapsed: false,
        },
        config
      );
      this.root = null;
      this.logContainer = null;
      this.statusEl = null;
      this.queryInput = null;
      this._buildUI();
    }

    _buildUI() {
      const container = document.createElement("div");
      container.className = "smartui-console";
      container.style.position = "fixed";
      container.style.zIndex = 99999;
      container.style.background = "rgba(20,22,30,0.95)";
      container.style.color = "#f5f7ff";
      container.style.fontFamily = "Inter, system-ui, sans-serif";
      container.style.fontSize = "12px";
      container.style.borderRadius = "12px 12px 0 0";
      container.style.boxShadow = "0 12px 30px rgba(0,0,0,0.35)";
      container.style.width = "320px";
      container.style.maxHeight = "60vh";
      container.style.display = "flex";
      container.style.flexDirection = "column";
      container.style.backdropFilter = "blur(4px)";
      container.style.transition = "transform 0.25s ease";
      if (this.config.position === "bottom-right") {
        container.style.right = "12px";
        container.style.bottom = "0";
      } else {
        container.style.left = "12px";
        container.style.bottom = "0";
      }

      const header = document.createElement("div");
      header.style.display = "flex";
      header.style.alignItems = "center";
      header.style.justifyContent = "space-between";
      header.style.padding = "10px 12px";
      header.style.cursor = "pointer";
      header.style.background = "rgba(40,42,60,0.85)";
      header.style.borderRadius = "12px 12px 0 0";
      header.innerHTML = `<span style="font-weight:600">SmartUI Agent</span><span class="status-dot" style="width:9px;height:9px;border-radius:50%;background:#f25252;display:inline-block;"></span>`;
      container.appendChild(header);

      const log = document.createElement("div");
      log.style.flex = "1";
      log.style.overflowY = "auto";
      log.style.padding = "10px 12px";
      log.style.display = "flex";
      log.style.flexDirection = "column";
      log.style.gap = "8px";
      container.appendChild(log);

      const queryWrap = document.createElement("div");
      queryWrap.style.display = "flex";
      queryWrap.style.gap = "6px";
      queryWrap.style.padding = "8px 10px 12px";
      queryWrap.style.borderTop = "1px solid rgba(255,255,255,0.08)";

      const input = document.createElement("input");
      input.type = "text";
      input.placeholder = "Ask about this session…";
      input.style.flex = "1";
      input.style.background = "rgba(255,255,255,0.08)";
      input.style.border = "1px solid rgba(255,255,255,0.1)";
      input.style.borderRadius = "6px";
      input.style.padding = "6px 8px";
      input.style.color = "#f5f7ff";
      input.style.outline = "none";
      queryWrap.appendChild(input);

      const askBtn = document.createElement("button");
      askBtn.textContent = "Ask";
      askBtn.style.background = "#6366f1";
      askBtn.style.border = "none";
      askBtn.style.color = "#fff";
      askBtn.style.borderRadius = "6px";
      askBtn.style.padding = "6px 12px";
      askBtn.style.cursor = "pointer";
      queryWrap.appendChild(askBtn);

      container.appendChild(queryWrap);

      document.body.appendChild(container);
      this.root = container;
      this.logContainer = log;
      this.statusEl = header.querySelector(".status-dot");
      this.queryInput = input;

      header.addEventListener("click", () => {
        if (container.dataset.collapsed === "true") {
          container.dataset.collapsed = "false";
          container.style.transform = "translateY(0)";
        } else {
          container.dataset.collapsed = "true";
          container.style.transform = "translateY(calc(100% - 36px))";
        }
      });

      askBtn.addEventListener("click", () => this._submitQuery());
      input.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter") {
          ev.preventDefault();
          this._submitQuery();
        }
      });

      if (this.config.collapsed) {
        container.dataset.collapsed = "true";
        container.style.transform = "translateY(calc(100% - 36px))";
      }
    }

    log(message, tone = "info") {
      if (!this.logContainer) return;
      const entry = document.createElement("div");
      entry.style.padding = "8px";
      entry.style.borderRadius = "8px";
      entry.style.background = tone === "warning" ? "rgba(252,211,77,0.12)" : "rgba(99,102,241,0.12)";
      entry.style.border = tone === "warning" ? "1px solid rgba(252,211,77,0.35)" : "1px solid rgba(99,102,241,0.3)";
      entry.innerHTML = `<div style="font-weight:600;margin-bottom:4px;">${tone === "warning" ? "⚠︎" : "•"} ${
        tone === "warning" ? "Agent Notice" : "Agent Update"
      }</div><div style="white-space:pre-wrap">${message}</div>`;
      this.logContainer.prepend(entry);
      if (this.logContainer.childElementCount > 200) {
        this.logContainer.removeChild(this.logContainer.lastChild);
      }
    }

    updateStatus(decision) {
      if (!this.statusEl) return;
      if (decision.shouldRecord) {
        this.statusEl.style.background = "#34d399";
      } else {
        this.statusEl.style.background = "#facc15";
      }
    }

    _submitQuery() {
      const value = this.queryInput.value.trim();
      if (!value) return;
      this.queryInput.value = "";
      const response = this.agent.answerQuery(value);
      this.log(`You asked: ${value}\nAgent: ${response}`, "info");
    }
  }

  /* ---------------------------------------------------------------------- */
  /* SmartUIAgent                                                           */
  /* ---------------------------------------------------------------------- */

  class SmartUIAgent {
    constructor(options = {}) {
      this.options = Object.assign(
        {
          enableScreenshots: false,
          autoStart: false,
          trackHover: true,
          maxEvents: 250,
          explainDecisions: true,
        },
        options
      );

      this.session = new SessionContext();
      this.decisionEngine = new DecisionEngine(options.decisionEngine);
      this.metadataCollector = new MetadataCollector({
        enableScreenshots: this.options.enableScreenshots,
        screenshotFullPage: options.fullPageScreenshots || false,
      });
      this.storage = new StorageManager(this);
      this.console = new ConversationInterface(this, options.console);
      this.observers = [];
      this.listeners = [];
      this.isRunning = false;
      this.domObserver = null;
      this.hoverTimer = null;

      if (this.options.autoStart) {
        this.start();
      }
    }

    start() {
      if (this.isRunning) return;
      this.isRunning = true;
      this.console.log("Agent activated. Monitoring significant interactions.");
      this._attachEventListeners();
      this._observeDom();
    }

    stop() {
      if (!this.isRunning) return;
      this.listeners.forEach(({ target, type, handler, options }) => target.removeEventListener(type, handler, options));
      this.listeners = [];
      if (this.domObserver) {
        this.domObserver.disconnect();
        this.domObserver = null;
      }
      this.isRunning = false;
      this.console.log("Agent stopped.", "warning");
    }

    async handleEvent(event, eventType) {
      if (!this.isRunning) return;

      const payload = this._buildPayload(event, eventType);
      const decision = this.decisionEngine.evaluate(payload, this.session);
      this.console.updateStatus(decision);

      if (!decision.shouldRecord) return;

      const record = {
        id: `SUA-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        eventType,
        timestamp: new Date().toISOString(),
        reason: decision.reason,
        score: decision.score,
        priority: decision.priority,
        anomaly: decision.anomaly,
        meta: payload.meta,
      };

      try {
        const metadata = await this.metadataCollector.collect(payload);
        record.metadata = metadata;
        this.session.updateWithEvent(record);
        this.console.log(`${eventType.toUpperCase()} captured: ${record.reason}`);
      } catch (err) {
        this.console.log(`Metadata collection failed: ${err?.message || err}`, "warning");
      }

      if (this.session.events.length > this.options.maxEvents) {
        this.console.log("Max event limit reached. Auto-stopping agent.", "warning");
        this.stop();
      }
    }

    answerQuery(query) {
      const q = query.toLowerCase();
      if (/summary|overview/.test(q)) {
        return `Captured ${this.session.events.length} significant interactions. Active intent: ${
          this.session.activeIntent || "unknown"
        }.`;
      }
      if (/anomal/.test(q)) {
        const anomalies = this.session.events.filter((ev) => ev.anomaly);
        if (!anomalies.length) return "No anomalies detected so far.";
        return `${anomalies.length} anomalies. Latest: ${anomalies[anomalies.length - 1].anomaly}`;
      }
      if (/last|recent/.test(q)) {
        const last = this.session.events[this.session.events.length - 1];
        if (!last) return "Nothing recorded yet.";
        return `Most recent: ${last.eventType} on ${last.meta.selector}. Reason: ${last.reason}`;
      }
      if (/export|download/.test(q)) {
        this.storage.exportSession();
        return "Export started.";
      }
      if (/test case|steps/.test(q)) {
        return this.storage.generateTestCaseDraft();
      }
      return "I monitor significant UI interactions, score them, and store rich metadata with explanations. Ask for a summary, anomalies, export, or test case.";
    }

    _attachEventListeners() {
      const types = ["click", "input", "change", "submit", "focus", "blur"];
      if (this.options.trackHover) types.push("mouseover");

      types.forEach((type) => {
        const handler = (ev) => {
          if (type === "mouseover") {
            this._handleHover(ev);
          } else {
            this.handleEvent(ev, type);
          }
        };
        document.addEventListener(type, handler, true);
        this.listeners.push({ target: document, type, handler, options: true });
      });
    }

    _handleHover(event) {
      clearTimeout(this.hoverTimer);
      this.hoverTimer = setTimeout(() => {
        this.handleEvent(event, "hover");
      }, 200);
    }

    _observeDom() {
      this.domObserver = new MutationObserver((mutations) => {
        if (!mutations.length) return;
        this.session.registerDomMutation();
      });
      this.domObserver.observe(document.body, { attributes: true, childList: true, subtree: true });
    }

    _buildPayload(event, eventType) {
      const target = event.target;
      const reference = target && target.nodeType === Node.TEXT_NODE ? target.parentElement : target;
      const tagName = reference ? reference.tagName : "UNKNOWN";
      const role = reference ? reference.getAttribute("role") : null;
      const dataset = reference ? Object.assign({}, reference.dataset) : {};
      const attributes = {};
      if (reference && reference.attributes) {
        Array.from(reference.attributes).forEach((attr) => {
          attributes[attr.name] = attr.value;
        });
      }

      const meta = {
        selector: generateCSSSelector(reference),
        xpath: generateXPath(reference),
        path: location.pathname,
        position: this._eventPosition(event),
        boundingRect: reference ? reference.getBoundingClientRect().toJSON() : null,
        isPrimaryAction: reference ? this._isPrimaryAction(reference) : false,
        formErrors: [],
      };

      if (eventType === "submit" && reference) {
        const form = reference;
        const invalids = Array.from(form.querySelectorAll(":invalid")).map((el) => el.name || el.id || el.tagName);
        meta.formErrors = invalids;
      }

      return {
        event,
        eventType,
        element: {
          reference,
          tagName,
          role,
          dataset,
          attributes,
          textContent: reference ? reference.textContent : "",
          textLength: reference ? (reference.textContent || "").length : 0,
          value: reference && "value" in reference ? reference.value : null,
        },
        meta,
      };
    }

    _eventPosition(event) {
      if (!event) return null;
      const { clientX, clientY } = event;
      return {
        clientX,
        clientY,
        scrollX: window.scrollX,
        scrollY: window.scrollY,
      };
    }

    _isPrimaryAction(element) {
      if (!element || !element.tagName) return false;
      const text = (element.textContent || "").toLowerCase();
      return (
        element.tagName === "BUTTON" ||
        element.tagName === "INPUT" ||
        /save|submit|confirm|continue|pay|login|checkout/.test(text)
      );
    }
  }

  /* ---------------------------------------------------------------------- */
  /* Public API                                                             */
  /* ---------------------------------------------------------------------- */

  window.SmartUIAgent = SmartUIAgent;
})();

