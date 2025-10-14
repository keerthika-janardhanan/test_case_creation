/*
 * SmartUIAgent - Agentic UI Action Recorder
 * ------------------------------------------------------------
 * This module implements an intelligent UI action recorder that selectively
 * captures high-value interactions with rich metadata and agentic reasoning.
 * It is designed to be imported as an ES module or injected via a bundler.
 *
 * Usage example:
 *   import { SmartUIAgent } from './SmartUIAgent.js';
 *   const agent = new SmartUIAgent();
 *   agent.start();
 *
 * The agent exposes conversational methods such as `ask(question)` and
 * `explainDecision(recordId)` to provide transparency into its decisions.
 */

const DEFAULT_OPTIONS = {
  autoStart: false,
  maxEventBuffer: 250,
  screenshot: {
    element: true,
    fullPage: false,
    scale: 0.6
  },
  sampling: {
    baseIntervalMs: 400,
    burstThreshold: 0.75,
    idleWindowMs: 5000
  },
  anomaly: {
    spikeThreshold: 5,
    idleThresholdMs: 120000
  },
  priorities: {
    criticalRoles: ['button', 'a', 'input', 'select', 'textarea', 'form'],
    ariaHighImpact: ['dialog', 'alert', 'navigation', 'banner'],
    minScoreToRecord: 0.35,
    dynamicKeywords: []
  }
};

const SESSION_STATE = {
  IDLE: 'idle',
  OBSERVING: 'observing',
  PAUSED: 'paused'
};

function mergeDeep(target, source) {
  if (!source) return target;
  const output = { ...target };
  Object.keys(source).forEach((key) => {
    const value = source[key];
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      output[key] = mergeDeep(target[key] || {}, value);
    } else {
      output[key] = value;
    }
  });
  return output;
}

class EventBuffer {
  constructor(limit) {
    this.limit = limit;
    this.items = [];
  }

  push(item) {
    this.items.push(item);
    if (this.items.length > this.limit) {
      this.items.shift();
    }
  }

  toArray() {
    return [...this.items];
  }
}

class SessionContext {
  constructor() {
    this.reset();
  }

  reset() {
    this.startTime = null;
    this.lastEventTime = null;
    this.eventCount = 0;
    this.highValueCount = 0;
    this.pageTransitions = [];
    this.workflowStages = [];
    this.intentHypothesis = 'exploration';
  }

  start() {
    this.startTime = performance.now();
    this.lastEventTime = this.startTime;
  }

  update(eventContext, decision) {
    const now = performance.now();
    this.eventCount += 1;
    this.lastEventTime = now;
    if (decision.shouldRecord) {
      this.highValueCount += 1;
    }

    if (eventContext.event.type === 'submit') {
      this.workflowStages.push({
        timestamp: now,
        description: 'Form submitted',
        targetSummary: eventContext.elementSummary
      });
      this.intentHypothesis = 'task_completion';
    }

    if (eventContext.event.type === 'click' && /checkout|buy|purchase/i.test(eventContext.textContent || '')) {
      this.intentHypothesis = 'transactional';
    }

    if (eventContext.navigation) {
      this.pageTransitions.push({
        timestamp: now,
        url: eventContext.navigation.url,
        title: document.title
      });
    }
  }
}

class DecisionEngine {
  constructor(options, context) {
    this.options = options;
    this.context = context;
    this.recentScores = new EventBuffer(20);
  }

  evaluate(eventContext) {
    const score = this.computeSignificanceScore(eventContext);
    this.recentScores.push({ time: performance.now(), score });

    const adaptiveThreshold = this.getAdaptiveThreshold();
    const shouldRecord = score >= Math.max(this.options.priorities.minScoreToRecord, adaptiveThreshold);

    const densityDecision = this.getSamplingDecision(eventContext, score);
    const anomaly = this.detectAnomaly(eventContext);

    return {
      shouldRecord,
      score,
      reason: this.buildReasoning(eventContext, score, adaptiveThreshold, densityDecision, anomaly),
      densityDecision,
      anomaly
    };
  }

  computeSignificanceScore(ctx) {
    const { event, textContent, metadata } = ctx;
    let score = 0;

    const semanticHints = [
      metadata.ariaRole,
      metadata.labels && metadata.labels.join(' '),
      metadata.placeholder,
      metadata.nameAttr,
      metadata.id
    ]
      .filter(Boolean)
      .join(' ')
      .toLowerCase();

    const highImpactRole = this.options.priorities.criticalRoles.includes(metadata.semanticRole);
    const ariaPriority = metadata.ariaRole && this.options.priorities.ariaHighImpact.includes(metadata.ariaRole);

    if (highImpactRole) score += 0.35;
    if (ariaPriority) score += 0.2;

    if (event.type === 'submit' || event.type === 'change') score += 0.2;
    if (event.type === 'click') score += 0.1;

    const textLength = (textContent || '').trim().length;
    if (textLength > 0 && textLength <= 40) score += 0.05;
    if (/save|submit|apply|confirm|checkout/i.test(textContent || '')) score += 0.25;
    if (/cancel|close/i.test(textContent || '')) score += 0.1;

    const dynamicKeywords = this.options.priorities.dynamicKeywords || [];
    const lowerText = (textContent || '').toLowerCase();
    dynamicKeywords.forEach(({ keyword, weight }) => {
      if (!keyword) return;
      if (lowerText.includes(keyword) || semanticHints.includes(keyword)) {
        score += weight;
      }
    });
    if (/password|email|username|search|address/i.test(semanticHints)) score += 0.15;
    if (/danger|warning|error/.test(metadata.classes)) score += 0.1;

    if (metadata.visibilityRatio < 0.5 || metadata.isObscured) score -= 0.15;
    if (metadata.isInteractive) score += 0.1;

    score += Math.min(0.2, metadata.domDepth * 0.005);

    return Math.max(0, Math.min(1, score));
  }

  getAdaptiveThreshold() {
    const recent = this.recentScores.toArray();
    if (!recent.length) return this.options.priorities.minScoreToRecord;

    const avg = recent.reduce((acc, item) => acc + item.score, 0) / recent.length;
    const dynamic = avg * 0.75;
    return Math.min(0.6, Math.max(0.2, dynamic));
  }

  getSamplingDecision(eventContext, score) {
    const now = performance.now();
    const sinceLast = now - (this.context.lastEventTime || now);
    const density = score >= this.options.sampling.burstThreshold ? 'high' : 'normal';

    let decision = 'record';
    if (density === 'high' && sinceLast < this.options.sampling.baseIntervalMs) {
      decision = 'throttle';
    }
    if (sinceLast > this.options.sampling.idleWindowMs) {
      decision = 'encourage';
    }

    return {
      density,
      action: decision,
      sinceLast
    };
  }

  detectAnomaly(eventContext) {
    const now = performance.now();
    const sinceLast = now - (this.context.lastEventTime || now);
    const anomaly = {
      type: null,
      active: false,
      details: null
    };

    if (sinceLast > this.options.anomaly.idleThresholdMs) {
      anomaly.type = 'idle';
      anomaly.active = true;
      anomaly.details = `No interactions for ${(sinceLast / 1000).toFixed(1)}s`;
    }

    if (eventContext.event.type === 'click' && eventContext.metadata.similarSiblingCount >= this.options.anomaly.spikeThreshold) {
      anomaly.type = 'spike';
      anomaly.active = true;
      anomaly.details = `High-density cluster (${eventContext.metadata.similarSiblingCount} similar elements)`;
    }

    return anomaly;
  }

  buildReasoning(ctx, score, threshold, densityDecision, anomaly) {
    const reasons = [];
    reasons.push(`score ${score.toFixed(2)} vs threshold ${threshold.toFixed(2)}`);
    if (ctx.metadata.semanticRole) reasons.push(`role=${ctx.metadata.semanticRole}`);
    if (ctx.metadata.ariaRole) reasons.push(`aria=${ctx.metadata.ariaRole}`);
    if (ctx.textContent) reasons.push(`text="${ctx.textContent.trim().slice(0, 40)}"`);
    if (densityDecision.action === 'throttle') reasons.push('throttled due to high density');
    if (densityDecision.action === 'encourage') reasons.push('spaced interaction (encouraged)');
    if (anomaly.active) reasons.push(`anomaly:${anomaly.type}`);
    return reasons.join(' | ');
  }
}

class MetadataCollector {
  constructor(options) {
    this.options = options;
  }

  async collect(eventSnapshot, element) {
    const rect = element.getBoundingClientRect();
    const styles = window.getComputedStyle(element);
    const visibilityRatio = this.computeVisibilityRatio(rect);
    const metadata = {
      tag: element.tagName.toLowerCase(),
      id: element.id || null,
      classes: element.className || null,
      nameAttr: element.getAttribute('name'),
      typeAttr: element.getAttribute('type'),
      placeholder: element.getAttribute('placeholder'),
      ariaRole: element.getAttribute('role'),
      semanticRole: this.getSemanticRole(element),
      isInteractive: this.isInteractive(element),
      domDepth: this.getDomDepth(element),
      visibilityRatio,
      isObscured: this.isObscured(rect),
      boundingRect: {
        top: rect.top,
        left: rect.left,
        width: rect.width,
        height: rect.height
      },
      styles: {
        color: styles.color,
        backgroundColor: styles.backgroundColor,
        fontSize: styles.fontSize,
        fontWeight: styles.fontWeight,
        zIndex: styles.zIndex,
        display: styles.display,
        visibility: styles.visibility,
        opacity: styles.opacity
      },
      labels: this.getLabelTexts(element),
      cssPath: this.getCssPath(element),
      xPath: this.getXPath(element),
      siblings: this.describeSiblings(element),
      parentSummary: this.describeParent(element),
      similarSiblingCount: this.countSimilarSiblings(element)
    };

    const textContent = this.extractTextContent(element);
    const screenshot = await this.captureScreenshots(element);

    return {
      event: eventSnapshot,
      metadata,
      textContent,
      screenshot,
      elementSummary: `${metadata.tag}${metadata.id ? `#${metadata.id}` : ''}${metadata.classes ? `.${metadata.classes}` : ''}`
    };
  }

  computeVisibilityRatio(rect) {
    const { innerWidth, innerHeight } = window;
    const viewportArea = innerWidth * innerHeight;
    const elementArea = rect.width * rect.height;
    if (viewportArea === 0) return 0;
    if (elementArea === 0) return 0;
    const visibleWidth = Math.min(rect.right, innerWidth) - Math.max(rect.left, 0);
    const visibleHeight = Math.min(rect.bottom, innerHeight) - Math.max(rect.top, 0);
    const visibleArea = Math.max(0, visibleWidth) * Math.max(0, visibleHeight);
    return Math.max(0, Math.min(1, visibleArea / elementArea));
  }

  isObscured(rect) {
    const centerX = rect.left + rect.width / 2;
    const centerY = rect.top + rect.height / 2;
    const elementAtPoint = document.elementFromPoint(centerX, centerY);
    return elementAtPoint && !rectContainsElement(rect, elementAtPoint) && elementAtPoint !== document.body;
  }

  getDomDepth(element) {
    let depth = 0;
    let node = element;
    while (node && node.parentElement) {
      depth += 1;
      node = node.parentElement;
    }
    return depth;
  }

  getLabelTexts(element) {
    const labels = [];
    if (element.labels) {
      element.labels.forEach((label) => labels.push(label.textContent.trim()));
    }
    const ariaLabelledBy = element.getAttribute('aria-labelledby');
    if (ariaLabelledBy) {
      ariaLabelledBy.split(' ').forEach((id) => {
        const el = document.getElementById(id);
        if (el) labels.push(el.textContent.trim());
      });
    }
    const ariaLabel = element.getAttribute('aria-label');
    if (ariaLabel) labels.push(ariaLabel.trim());
    return labels;
  }

  extractTextContent(element) {
    if (['input', 'textarea'].includes(element.tagName.toLowerCase())) {
      return element.value || element.getAttribute('placeholder') || '';
    }
    return element.textContent || '';
  }

  getCssPath(element) {
    const path = [];
    let node = element;
    while (node && node.nodeType === Node.ELEMENT_NODE) {
      let selector = node.nodeName.toLowerCase();
      if (node.id) {
        selector += `#${node.id}`;
        path.unshift(selector);
        break;
      } else {
        const siblingIndex = Array.from(node.parentNode ? node.parentNode.children : []).indexOf(node) + 1;
        selector += `:nth-child(${siblingIndex})`;
      }
      path.unshift(selector);
      node = node.parentElement;
    }
    return path.join(' > ');
  }

  getXPath(element) {
    const segments = [];
    let node = element;
    while (node && node.nodeType === Node.ELEMENT_NODE) {
      const siblings = Array.from(node.parentNode ? node.parentNode.children : []).filter((child) => child.nodeName === node.nodeName);
      const index = siblings.indexOf(node) + 1;
      segments.unshift(`${node.nodeName.toLowerCase()}[${index}]`);
      node = node.parentElement;
    }
    return `/${segments.join('/')}`;
  }

  describeSiblings(element) {
    const siblings = [];
    if (!element.parentElement) return siblings;
    Array.from(element.parentElement.children).forEach((sibling) => {
      if (sibling === element) return;
      siblings.push({
        tag: sibling.tagName.toLowerCase(),
        classes: sibling.className || null,
        id: sibling.id || null
      });
    });
    return siblings;
  }

  describeParent(element) {
    if (!element.parentElement) return null;
    const parent = element.parentElement;
    return {
      tag: parent.tagName.toLowerCase(),
      id: parent.id || null,
      classes: parent.className || null,
      role: parent.getAttribute('role')
    };
  }

  countSimilarSiblings(element) {
    if (!element.parentElement) return 0;
    const tag = element.tagName;
    const cls = element.className;
    return Array.from(element.parentElement.children).filter((sibling) => sibling !== element && sibling.tagName === tag && sibling.className === cls).length;
  }

  getSemanticRole(element) {
    const role = element.getAttribute('role');
    if (role) return role;
    const tag = element.tagName.toLowerCase();
    const roleMap = {
      a: 'link',
      button: 'button',
      input: 'textbox',
      select: 'listbox',
      textarea: 'textbox',
      form: 'form',
      nav: 'navigation',
      header: 'banner',
      footer: 'contentinfo'
    };
    return roleMap[tag] || tag;
  }

  isInteractive(element) {
    const tag = element.tagName.toLowerCase();
    const interactiveTags = ['button', 'a', 'input', 'select', 'textarea', 'details', 'summary'];
    if (interactiveTags.includes(tag)) return true;
    const tabIndex = element.getAttribute('tabindex');
    return tabIndex !== null && tabIndex !== '-1';
  }

  async captureScreenshots(element) {
    if (typeof html2canvas !== 'function') {
      return {
        element: null,
        fullPage: null,
        note: 'html2canvas unavailable'
      };
    }

    const screenshots = {};
    try {
      if (this.options.screenshot.element) {
        const canvas = await html2canvas(element, { scale: this.options.screenshot.scale, useCORS: true });
        screenshots.element = canvas.toDataURL('image/webp', 0.7);
      }
      if (this.options.screenshot.fullPage) {
        const canvas = await html2canvas(document.body, { scale: this.options.screenshot.scale, useCORS: true });
        screenshots.fullPage = canvas.toDataURL('image/webp', 0.5);
      }
    } catch (error) {
      screenshots.note = `Screenshot failed: ${error.message}`;
    }
    return screenshots;
  }
}

class UIController {
  constructor(agent) {
    this.agent = agent;
    this.panel = null;
    this.statusIndicator = null;
    this.logList = null;
    this.queryInput = null;
    this.answerOutput = null;
  }

  mount() {
    if (this.panel) return;
    this.injectStyles();
    this.panel = document.createElement('div');
    this.panel.className = 'smart-ui-agent-panel';
    this.panel.innerHTML = `
      <div class="smart-ui-agent-header">
        <span class="smart-ui-agent-title">Smart UI Agent</span>
        <span class="smart-ui-agent-status" data-status="${this.agent.state}"></span>
      </div>
      <div class="smart-ui-agent-controls">
        <button data-action="toggle">${this.agent.state === SESSION_STATE.OBSERVING ? 'Pause' : 'Start'}</button>
        <button data-action="export">Export Session</button>
        <button data-action="clear">Clear</button>
      </div>
      <div class="smart-ui-agent-log"></div>
      <div class="smart-ui-agent-query">
        <input type="text" placeholder="Ask about this session..." />
        <button data-action="ask">Ask</button>
      </div>
      <div class="smart-ui-agent-answer" aria-live="polite"></div>
    `;

    document.body.appendChild(this.panel);
    this.statusIndicator = this.panel.querySelector('.smart-ui-agent-status');
    this.logList = this.panel.querySelector('.smart-ui-agent-log');
    this.queryInput = this.panel.querySelector('.smart-ui-agent-query input');
    this.answerOutput = this.panel.querySelector('.smart-ui-agent-answer');

    this.panel.addEventListener('click', (event) => {
      const action = event.target.getAttribute('data-action');
      if (!action) return;
      if (action === 'toggle') {
        if (this.agent.state === SESSION_STATE.OBSERVING) {
          this.agent.pause();
        } else {
          this.agent.start();
        }
      }
      if (action === 'export') {
        this.agent.exportSession();
      }
      if (action === 'clear') {
        this.agent.clearSession();
      }
      if (action === 'ask') {
        this.handleAsk();
      }
    });
  }

  injectStyles() {
    if (document.querySelector('style[data-smart-ui-agent]')) return;
    const style = document.createElement('style');
    style.setAttribute('data-smart-ui-agent', '');
    style.textContent = `
      .smart-ui-agent-panel {
        position: fixed;
        bottom: 16px;
        right: 16px;
        width: 320px;
        max-height: 60vh;
        font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        background: rgba(20, 21, 26, 0.92);
        color: #f5f5f5;
        border-radius: 12px;
        box-shadow: 0 12px 32px rgba(0, 0, 0, 0.35);
        overflow: hidden;
        z-index: 999999;
        backdrop-filter: blur(6px);
      }
      .smart-ui-agent-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 12px 16px;
        background: rgba(255, 255, 255, 0.04);
        border-bottom: 1px solid rgba(255, 255, 255, 0.06);
      }
      .smart-ui-agent-title {
        font-size: 15px;
        font-weight: 600;
      }
      .smart-ui-agent-status::before {
        content: attr(data-status);
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #9bdcf9;
      }
      .smart-ui-agent-controls {
        display: flex;
        gap: 8px;
        padding: 12px 16px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.06);
      }
      .smart-ui-agent-controls button {
        flex: 1;
        padding: 6px 10px;
        border-radius: 8px;
        border: 1px solid rgba(255, 255, 255, 0.12);
        background: rgba(255, 255, 255, 0.08);
        color: inherit;
        cursor: pointer;
        font-size: 13px;
        transition: background 0.2s ease, transform 0.2s ease;
      }
      .smart-ui-agent-controls button:hover {
        background: rgba(155, 220, 249, 0.2);
        transform: translateY(-1px);
      }
      .smart-ui-agent-log {
        padding: 12px 16px;
        overflow-y: auto;
        max-height: 200px;
        display: flex;
        flex-direction: column;
        gap: 8px;
      }
      .smart-ui-agent-log-item {
        background: rgba(255, 255, 255, 0.04);
        border-radius: 8px;
        padding: 8px 10px;
        display: grid;
        grid-template-columns: auto 1fr;
        gap: 4px 8px;
        font-size: 12px;
        line-height: 1.4;
      }
      .smart-ui-agent-log-item strong {
        color: #9bdcf9;
      }
      .smart-ui-agent-log-item span {
        grid-column: span 2;
        color: #ffffff;
      }
      .smart-ui-agent-log-item em {
        grid-column: span 2;
        color: rgba(255, 255, 255, 0.7);
        font-style: normal;
      }
      .smart-ui-agent-query {
        display: flex;
        gap: 8px;
        padding: 12px 16px;
        border-top: 1px solid rgba(255, 255, 255, 0.06);
        border-bottom: 1px solid rgba(255, 255, 255, 0.06);
      }
      .smart-ui-agent-query input {
        flex: 1;
        padding: 6px 8px;
        border-radius: 6px;
        border: 1px solid rgba(255, 255, 255, 0.14);
        background: rgba(0, 0, 0, 0.25);
        color: inherit;
        font-size: 12px;
      }
      .smart-ui-agent-query button {
        padding: 6px 10px;
        border-radius: 6px;
        border: 1px solid rgba(255, 255, 255, 0.12);
        background: rgba(155, 220, 249, 0.2);
        color: inherit;
        cursor: pointer;
      }
      .smart-ui-agent-answer {
        padding: 12px 16px;
        font-size: 12px;
        color: rgba(255, 255, 255, 0.8);
        min-height: 32px;
      }
    `;
    document.head.appendChild(style);
  }

  handleAsk() {
    if (!this.queryInput) return;
    const question = this.queryInput.value.trim();
    if (!question) return;
    if (/^note:/i.test(question)) {
      const feedback = question.replace(/^note:/i, '').trim();
      const reply = this.agent.recordFeedback(feedback);
      if (this.answerOutput) this.answerOutput.textContent = reply;
      this.queryInput.value = '';
      return;
    }
    if (/^focus:/i.test(question)) {
      const keyword = question.replace(/^focus:/i, '').trim();
      const reply = this.agent.addPriorityKeyword(keyword, 0.2);
      if (this.answerOutput) this.answerOutput.textContent = reply;
      this.queryInput.value = '';
      return;
    }
    const answer = this.agent.ask(question);
    if (this.answerOutput) {
      this.answerOutput.textContent = answer;
    }
  }

  updateStatus(state) {
    if (!this.statusIndicator) return;
    this.statusIndicator.setAttribute('data-status', state);
    const toggleButton = this.panel && this.panel.querySelector('button[data-action="toggle"]');
    if (toggleButton) {
      toggleButton.textContent = state === SESSION_STATE.OBSERVING ? 'Pause' : 'Start';
    }
  }

  appendLog(record) {
    if (!this.panel) this.mount();
    if (!this.logList) return;
    const item = document.createElement('div');
    item.className = 'smart-ui-agent-log-item';
    item.innerHTML = `
      <strong>${record.eventType}</strong>
      <span>${record.targetSummary}</span>
      <em>${record.reason}</em>
    `;
    this.logList.prepend(item);
  }

  clearLog() {
    if (this.logList) {
      this.logList.innerHTML = '';
    }
    if (this.answerOutput) {
      this.answerOutput.textContent = '';
    }
  }

  teardown() {
    if (this.panel) {
      this.panel.remove();
      this.panel = null;
    }
  }
}

class StorageManager {
  constructor(maxBuffer) {
    this.maxBuffer = maxBuffer;
    this.records = [];
    this.insights = [];
    this.environment = null;
  }

  addRecord(record) {
    this.records.push(record);
    if (this.records.length > this.maxBuffer) {
      this.records.shift();
    }
  }

  addInsight(insight) {
    this.insights.push({ ...insight, timestamp: new Date().toISOString() });
  }

  setEnvironment(env) {
    this.environment = { ...env };
  }

  toJSON() {
    return {
      version: '1.0.0',
      generatedAt: new Date().toISOString(),
      environment: this.environment,
      records: this.records,
      insights: this.insights
    };
  }

  clear() {
    this.records = [];
    this.insights = [];
  }
}

function rectContainsElement(rect, element) {
  const elRect = element.getBoundingClientRect();
  return (
    elRect.top >= rect.top &&
    elRect.left >= rect.left &&
    elRect.bottom <= rect.bottom &&
    elRect.right <= rect.right
  );
}

function snapshotEvent(event) {
  const target = event.target instanceof Element ? event.target : null;
  return {
    type: event.type,
    timeStamp: event.timeStamp,
    detail: event.detail ?? null,
    key: event.key ?? null,
    code: event.code ?? null,
    button: typeof event.button === 'number' ? event.button : null,
    buttons: typeof event.buttons === 'number' ? event.buttons : null,
    value: target && 'value' in target ? target.value : null,
    pointerType: event.pointerType ?? null,
    clientX: typeof event.clientX === 'number' ? event.clientX : null,
    clientY: typeof event.clientY === 'number' ? event.clientY : null,
    metaKey: !!event.metaKey,
    altKey: !!event.altKey,
    ctrlKey: !!event.ctrlKey,
    shiftKey: !!event.shiftKey,
    targetTag: target ? target.tagName.toLowerCase() : null,
    targetId: target ? target.id || null : null,
    targetClasses: target ? target.className || null : null
  };
}

function normalizeEventType(type) {
  switch (type) {
    case 'pointerover':
      return 'hover';
    case 'focusin':
      return 'focus';
    case 'focusout':
      return 'blur';
    default:
      return type;
  }
}

function downloadFile(filename, data, mime = 'application/json') {
  const blob = new Blob([data], { type: mime });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export class SmartUIAgent {
  constructor(options = {}) {
    this.options = mergeDeep(DEFAULT_OPTIONS, options);
    this.state = SESSION_STATE.IDLE;

    this.context = new SessionContext();
    this.decisionEngine = new DecisionEngine(this.options, this.context);
    this.metadataCollector = new MetadataCollector(this.options);
    this.storage = new StorageManager(this.options.maxEventBuffer);
    this.options.priorities.dynamicKeywords = this.options.priorities.dynamicKeywords || [];
    this.ui = new UIController(this);

    this.eventHandler = this.handleEvent.bind(this);
    this.activeListeners = [];
    this.observer = null;

    this.lastDecision = null;

    if (this.options.autoStart) {
      this.start();
    }
  }

  start() {
    if (this.state === SESSION_STATE.OBSERVING) return;
    if (this.state === SESSION_STATE.IDLE) {
      this.context.reset();
      this.context.start();
    }
    this.state = SESSION_STATE.OBSERVING;
    // Capture environment snapshot at start
    try {
      const env = this.getEnvironmentSnapshot();
      this.storage.setEnvironment(env);
    } catch (_) { /* noop */ }
    this.attachListeners();
    this.ui.mount();
    this.ui.updateStatus(this.state);
    this.storage.addInsight({
      type: 'status',
      message: 'Observation started'
    });
  }

  pause() {
    if (this.state !== SESSION_STATE.OBSERVING) return;
    this.detachListeners();
    this.state = SESSION_STATE.PAUSED;
    this.ui.updateStatus(this.state);
    this.storage.addInsight({ type: 'status', message: 'Observation paused' });
  }

  stop() {
    if (this.state === SESSION_STATE.IDLE) return;
    this.detachListeners();
    this.state = SESSION_STATE.IDLE;
    this.ui.updateStatus(this.state);
    this.storage.addInsight({ type: 'status', message: 'Observation stopped' });
  }

  clearSession() {
    this.storage.clear();
    this.context.reset();
    this.lastDecision = null;
    this.ui.clearLog();
    this.storage.addInsight({ type: 'status', message: 'Session cleared' });
  }

  recordFeedback(feedback) {
    const message = (feedback || '').trim();
    if (!message) {
      return 'Please provide feedback after "note:".';
    }
    this.storage.addInsight({ type: 'feedback', message });
    return 'Thanks, your feedback will influence future recording choices.';
  }

  addPriorityKeyword(keyword, weight = 0.15) {
    const term = (keyword || '').trim();
    if (!term) {
      return 'Please provide a keyword after "focus:".';
    }
    const normalized = term.toLowerCase();
    const list = this.options.priorities.dynamicKeywords;
    const existing = list.find((entry) => entry.keyword === normalized);
    if (existing) {
      existing.weight = weight;
    } else {
      list.push({ keyword: normalized, weight });
    }
    this.storage.addInsight({ type: 'guidance', message: `Boosting focus on "${normalized}"`, weight });
    return `Understood. Interactions mentioning "${normalized}" will receive extra weight.`;
  }

  attachListeners() {
    const events = ['click', 'input', 'change', 'submit', 'focus', 'blur', 'pointerover'];
    events.forEach((eventName) => {
      const listener = (event) => this.eventHandler(event);
      document.addEventListener(eventName, listener, true);
      this.activeListeners.push({ eventName, listener });
    });

    if (!this.observer) {
      this.observer = new MutationObserver((mutations) => {
        const interesting = mutations.filter((mutation) => mutation.type === 'childList' || mutation.type === 'attributes');
        if (interesting.length) {
          this.storage.addInsight({
            type: 'dom_change',
            message: `${interesting.length} structural changes detected`,
            detail: interesting.slice(0, 5).map((m) => ({
              type: m.type,
              target: m.target ? m.target.tagName : 'unknown'
            }))
          });
        }
      });
      this.observer.observe(document.body, {
        childList: true,
        subtree: true,
        attributes: true,
        attributeFilter: ['class', 'style', 'aria-hidden', 'disabled']
      });
    }
  }

  detachListeners() {
    this.activeListeners.forEach(({ eventName, listener }) => {
      document.removeEventListener(eventName, listener, true);
    });
    this.activeListeners = [];
    if (this.observer) {
      this.observer.disconnect();
      this.observer = null;
    }
  }

  async handleEvent(event) {
    if (this.state !== SESSION_STATE.OBSERVING) return;
    if (!(event.target instanceof Element)) return;

    const element = event.target;

    const eventSnapshot = snapshotEvent(event);
    const eventContext = await this.metadataCollector.collect(eventSnapshot, element);
    eventContext.navigation = this.detectNavigation(event);

    const decision = this.decisionEngine.evaluate(eventContext);
    this.lastDecision = decision;
    this.context.update(eventContext, decision);

    if (decision.anomaly.active) {
      this.storage.addInsight({
        type: 'anomaly',
        severity: decision.anomaly.type === 'spike' ? 'medium' : 'low',
        message: decision.anomaly.details
      });
    }

    if (!decision.shouldRecord || decision.densityDecision.action === 'throttle') {
      return;
    }

    const record = this.buildRecord(eventContext, decision);
    this.storage.addRecord(record);
    this.ui.appendLog(record);
  }

  detectNavigation(event) {
    if (event.type !== 'click') return null;
    const anchor = event.target.closest('a[href]');
    if (!anchor) return null;
    const url = anchor.href;
    const samePage = url.startsWith('#') || url === window.location.href;
    if (samePage) return null;
    return {
      url,
      anticipated: true
    };
  }

  buildRecord(eventContext, decision) {
    const { event, metadata, textContent, screenshot, elementSummary } = eventContext;
    return {
      id: `${event.timeStamp}-${Math.random().toString(16).slice(2, 8)}`,
      timestamp: new Date().toISOString(),
      eventType: normalizeEventType(event.type),
      targetSummary: elementSummary,
      textContent,
      metadata,
      screenshot,
      reason: decision.reason,
      score: decision.score,
      anomaly: decision.anomaly,
      context: {
        densityDecision: decision.densityDecision,
        workflowStage: this.context.workflowStages.slice(-1)[0] || null,
        intentHypothesis: this.context.intentHypothesis
      }
    };
  }

  explainDecision(recordId) {
    const record = this.storage.records.find((item) => item.id === recordId);
    if (!record) return 'No record found for the provided identifier.';
    const parts = [
      `Event ${record.eventType} on ${record.targetSummary}`,
      `Score ${record.score.toFixed(2)} (reason: ${record.reason})`
    ];
    if (record.context.intentHypothesis) {
      parts.push(`Intent hypothesis: ${record.context.intentHypothesis}`);
    }
    if (record.anomaly && record.anomaly.active) {
      parts.push(`Anomaly detected: ${record.anomaly.details}`);
    }
    return parts.join('. ');
  }

  ask(question) {
    const q = question.toLowerCase();
    if (/last decision/.test(q) && this.lastDecision) {
      return `Last decision score ${this.lastDecision.score.toFixed(2)} because ${this.lastDecision.reason}`;
    }
    if (/summary|overview/.test(q)) {
      return this.buildSessionSummary();
    }
    if (/intent/.test(q)) {
      return `Current intent hypothesis: ${this.context.intentHypothesis}`;
    }
    if (/(keyword|focus area|focus areas)/.test(q)) {
      return this.describePriorityKeywords();
    }
    if (/anomal/.test(q)) {
      const lastAnomaly = [...this.storage.insights].reverse().find((insight) => insight.type === 'anomaly');
      if (lastAnomaly) {
        return `Most recent anomaly: ${lastAnomaly.message}`;
      }
      return 'No anomalies detected so far.';
    }
    if (/why did you record/.test(q)) {
      const lastRecord = this.storage.records[this.storage.records.length - 1];
      if (lastRecord) {
        return this.explainDecision(lastRecord.id);
      }
      return 'No records captured yet to explain.';
    }
    return 'I am monitoring interactions and prioritizing significant events. Ask about summary, anomalies, intent, or decisions.';
  }

  describePriorityKeywords() {
    const dynamic = this.options.priorities.dynamicKeywords || [];
    if (!dynamic.length) {
      return 'No custom focus keywords applied yet. Use "focus: <keyword>" to add one.';
    }
    const parts = dynamic.map((entry) => `${entry.keyword} (+${entry.weight.toFixed(2)})`);
    return `Currently emphasizing: ${parts.join(', ')}`;
  }

  buildSessionSummary() {
    const durationMs = this.context.lastEventTime && this.context.startTime ? this.context.lastEventTime - this.context.startTime : 0;
    const duration = `${(durationMs / 1000).toFixed(1)}s`;
    const recordCount = this.storage.records.length;
    const highValueRate = this.context.eventCount ? (this.context.highValueCount / this.context.eventCount) * 100 : 0;
    return `Session duration ${duration}, recorded ${recordCount} high-value events (${highValueRate.toFixed(1)}% of ${this.context.eventCount} observed interactions). Intent: ${this.context.intentHypothesis}.`;
  }

  async exportSession() {
    const data = this.storage.toJSON();
    downloadFile(`smart-ui-session-${Date.now()}.json`, JSON.stringify(data, null, 2));

    const screenshots = data.records
      .map((record, index) => record.screenshot && record.screenshot.element ? `Screenshot ${index + 1} (element): ${record.screenshot.element.slice(0, 80)}...` : null)
      .filter(Boolean);

    if (screenshots.length) {
      const report = this.buildAnalysisReport(data, screenshots);
      downloadFile(`smart-ui-session-${Date.now()}-report.txt`, report, 'text/plain');
    }
  }

  buildAnalysisReport(data, screenshotNotes) {
    const lines = [];
    lines.push('Smart UI Agent Session Report');
    lines.push(`Generated: ${new Date().toISOString()}`);
    lines.push(`Total records: ${data.records.length}`);
    lines.push('');
    data.records.forEach((record, index) => {
      lines.push(`Event ${index + 1}: ${record.eventType} -> ${record.targetSummary}`);
      lines.push(`  Score: ${record.score.toFixed(2)} | Reason: ${record.reason}`);
      lines.push(`  Intent hypothesis: ${record.context.intentHypothesis}`);
      if (record.anomaly && record.anomaly.active) {
        lines.push(`  Anomaly: ${record.anomaly.details}`);
      }
      lines.push('');
    });
    lines.push('Screenshots:');
    screenshotNotes.forEach((note) => lines.push(`  ${note}`));
    return lines.join('\n');
  }

  destroy() {
    this.stop();
    this.ui.teardown();
  }

  // ---------------------- Environment & Test Cases ----------------------
  getEnvironmentSnapshot() {
    const navEntry = (performance.getEntriesByType && performance.getEntriesByType('navigation')[0]) || null;
    const viewport = { width: window.innerWidth, height: window.innerHeight, dpr: window.devicePixelRatio || 1 };
    const timing = navEntry ? {
      type: navEntry.type,
      startTime: navEntry.startTime,
      domContentLoaded: navEntry.domContentLoadedEventEnd,
      loadEventEnd: navEntry.loadEventEnd,
      responseEnd: navEntry.responseEnd
    } : null;
    return {
      url: location.href,
      title: document.title,
      referrer: document.referrer || null,
      userAgent: navigator.userAgent,
      language: navigator.language,
      platform: navigator.platform,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || null,
      viewport,
      timing,
      capturedAt: new Date().toISOString()
    };
  }

  generateTestCases() {
    // Map recorded events to structured manual test steps
    const steps = [];
    let stepIndex = 1;
    const toLabel = (rec) => (rec.textContent && rec.textContent.trim()) || rec.metadata.labels?.[0] || rec.metadata.placeholder || rec.metadata.nameAttr || rec.metadata.id || rec.metadata.tag;
    const toAction = (type, meta) => {
      switch (type) {
        case 'submit': return 'Submit Form';
        case 'change': return 'Update Field';
        case 'input': return 'Enter Data';
        case 'click': return meta.semanticRole === 'link' ? 'Follow Link' : 'Click';
        case 'hover': return 'Hover';
        case 'focus': return 'Focus Field';
        case 'blur': return 'Leave Field';
        default: return type.charAt(0).toUpperCase() + type.slice(1);
      }
    };
    const toExpected = (type, txt) => {
      if (type === 'submit') return 'Form submitted and response displayed.';
      if (type === 'change' || type === 'input') return 'Value accepted and rendered.';
      if (/save|apply|confirm|checkout/i.test(txt || '')) return 'Action acknowledged by the UI.';
      if (type === 'click') return 'Control responds and state updates.';
      return '';
    };
    this.storage.records.forEach((rec) => {
      const label = toLabel(rec);
      const action = toAction(rec.eventType, rec.metadata);
      const navText = `${action} ${label ? `'${label}'` : rec.targetSummary}`.trim();
      steps.push({
        step: stepIndex++,
        action,
        navigation: navText,
        data: rec.eventType === 'input' || rec.eventType === 'change' ? (rec.textContent || '') : '',
        expected: toExpected(rec.eventType, rec.textContent)
      });
    });
    return {
      id: `TC-${Date.now()}`,
      title: document.title || 'Recorded Scenario',
      type: 'positive',
      preconditions: [
        `Navigate to ${location.href}`,
        'User has required access and test data available.'
      ],
      step_details: steps,
      steps: steps.map((s) => `${s.action} - ${s.navigation}${s.data ? ` | Data: ${s.data}` : ''}${s.expected ? ` | Expected: ${s.expected}` : ''}`),
      data: {},
      expected: steps.length ? steps[steps.length - 1].expected : '',
      tags: ['recorded', 'smart-ui-agent'],
      assumptions: []
    };
  }

  exportTestCases(format = 'json') {
    const tc = this.generateTestCases();
    if (format === 'json') {
      downloadFile(`smart-ui-tests-${Date.now()}.json`, JSON.stringify([tc], null, 2));
      return;
    }
    if (format === 'csv') {
      const headers = ['SL','Action','Navigation Steps','Key Data Element Examples','Expected Results'];
      const rows = tc.step_details.map((d, idx) => [idx + 1, d.action, escapeCsv(d.navigation), escapeCsv(d.data), escapeCsv(d.expected)]);
      const csv = [headers.join(','), ...rows.map((r) => r.join(','))].join('\n');
      downloadFile(`smart-ui-tests-${Date.now()}.csv`, csv, 'text/csv');
    }
  }
}

export default SmartUIAgent;

// ---------------------- Helpers ----------------------
function escapeCsv(text) {
  const s = (text == null ? '' : String(text));
  if (/[",\n]/.test(s)) {
    return '"' + s.replace(/"/g, '""') + '"';
  }
  return s;
}

