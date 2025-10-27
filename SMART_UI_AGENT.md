# Smart UI Agent

The **SmartUIAgent** is a browser-side intelligent recorder that observes user interactions, scores their significance in real time, and selectively captures only the highest value events with rich metadata. It is designed to plug into existing web applications without external framework dependencies.

[For the complementary agentic playback/generation pipeline, see `docs/AGENTIC_TEST_SCRIPT_ENGINEER.md`.]

## Getting Started

1. Copy `app/SmartUIAgent.js` into your web project and ensure it is loaded as an ES module:
   ```html
   <script type="module">
     import { SmartUIAgent } from './SmartUIAgent.js';
     const agent = new SmartUIAgent({ autoStart: true });
     window.smartAgent = agent; // optional for debugging
   </script>
   ```
2. Provide [`html2canvas`](https://html2canvas.hertzen.com/) on the page if you want screenshot capture. Without it, the agent still operates and annotates the limitation in the metadata.
3. Interact with your application. The floating Smart UI Agent panel appears in the lower-right corner with controls to pause/resume, export the session, clear captured data, and query the agent in natural language.

## Agentic Intelligence Highlights

- **Intelligent Observation**: Monitors clicks, form inputs, submits, focus changes, and hovers. A mutation observer summarizes structural DOM changes to maintain context.
- **Decision Engine**: Scores each event using semantic cues (roles, labels, text, interactivity) and context awareness (workflow stages, recent density, anomalies). Adaptive thresholds prevent oversampling while prioritizing business-critical flows.
- **Rich Metadata**: Captures CSS selectors, XPath, bounding metrics, computed styles, labels, sibling/parent relationships, DOM depth, visibility, screenshot data (when available), and intent hypotheses.
- **AI-Enhanced Insights**: Maintains a running intent hypothesis, flags anomalies such as idle gaps or high-density clusters, and records narrative insights for later analysis.
- **Conversational Transparency**: Users can ask questions like “Why did you record the last event?” or “Any anomalies so far?” and receive contextual explanations sourced from the agent’s reasoning trail.

## Key Options

```js
const agent = new SmartUIAgent({
  maxEventBuffer: 300,
  screenshot: { element: true, fullPage: false, scale: 0.75 },
  sampling: { baseIntervalMs: 500, burstThreshold: 0.8, idleWindowMs: 6000 },
  anomaly: { spikeThreshold: 6, idleThresholdMs: 90000 },
  priorities: {
    criticalRoles: ['button', 'form', 'input', 'a'],
    ariaHighImpact: ['dialog', 'navigation'],
    minScoreToRecord: 0.4
  }
});
```

- **maxEventBuffer** – Maximum retained high-value events.
- **screenshot** – Controls element-level and full-page capture, including scaling.
- **sampling** – Tuning for adaptive density control.
- **anomaly** – Thresholds for idle detection and clustered activity.
- **priorities** – Domain-specific hints for weighting semantic importance.

## Runtime Controls & API

- `agent.start()` / `agent.pause()` / `agent.stop()` – Manage observation lifecycle.
- `agent.clearSession()` – Reset context and wipe captured data (UI log clears as well).
- `agent.exportSession()` – Download structured JSON plus a textual insight report.
- `agent.ask(question)` – Natural-language questions about the session (summary, anomalies, decisions, intent).
- `agent.explainDecision(recordId)` – Detailed justification for a captured record.
- `agent.destroy()` – Tear down listeners and UI when removing the agent.

## Data Outputs

Exported JSON includes:

- Event metadata with computed significance scores and reasoning trail.
- DOM structure descriptors (CSS path, XPath, relationships).
- Visual context (bounding rectangles, computed styles, screenshot data URIs).
- Agent insights (anomalies, DOM change summaries, status updates).

A companion text report summarizes each recorded event with human-readable explanations and screenshot references.

## Integration Tips

- Instantiate once per page load to avoid duplicate overlays.
- Provide domain-specific keywords (e.g., “claim”, “policy”, “checkout”) by extending `priorities` or adjusting thresholds to emphasize critical workflows.
- Extend the `DecisionEngine` or `MetadataCollector` classes to incorporate custom heuristics without modifying the main `SmartUIAgent` orchestration logic.
- Use the `StorageManager` records to feed automated test generation or analytics pipelines.

By combining selective capture with reasoning transparency, the Smart UI Agent accelerates authoring of AI-generated test cases, UX audits, and workflow analytics.
