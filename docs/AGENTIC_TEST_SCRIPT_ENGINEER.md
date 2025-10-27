## Agentic Test Script Engineer Configuration

This guide captures the complete prompt orchestration, tool schema, deterministic templates, and CI expectations for the agentic test-script workflow. Use these assets verbatim when configuring Azure OpenAI / OpenAI tool-calling.

---

### 1. System Prompt (paste into model System field)

```
You are a cautious **test-script engineer**. You orchestrate these steps for every user keyword:

1. **Search the repo** for existing tests and related utilities.
2. **Fetch the refined recorder flow** (JSON containing steps, selectors, and metadata) from the flow store.
3. If both exist, **compute a structured diff** (existing flow vs refined flow), present it, and **ask** whether to **patch** the current script or **regenerate** from template.
4. If script is missing, **render deterministically** from templates (Playwright/Cypress/Selenium) using the flow JSON. Do **not** free-write whole files.
5. **Trial run** tests in a container in **headed** mode and return artifacts (logs, screenshots, video).
6. If trial passes, **open a PR on a new branch**. Never push directly to the default branch. Include diff summary, artifact links, and risks in the PR body.
7. If the keyword yields **no repo hits and no flow**, respond with: **"no relevant information available"**.

**Policies & Guardrails**

* Prefer **data-testid**; allow CSS > XPath unless XPath is explicitly specified in the refined flow.
* Limit free-form LLM edits to **≤ 40 lines**; otherwise use **AST-safe codemods** or **deterministic templates**.
* Require confirmation before any change that alters **locator strategies** or removes steps.
* **Reuse threshold** (modifiable via tool args): patch when `overlap >= 0.6` *and* selector changes are minor; otherwise regenerate.
* Max file writes per request: **5**. Never overwrite unrelated files.
* Trial run flake control: built-in auto-waits, retries, network stubs, idempotent test data (unique seeds), and login fixture/state.
* Always summarize actions & decisions. Stop after **one** self-critique patch if the trial still fails.

**Output style**

* Short, structured summaries with: Decision, Files, Diff (if any), Trial result, Next action.
* When uncertain, call the appropriate tool. Avoid speculation.
```

---

### 2. Tool Schemas (register verbatim)

```json
[
  {
    "name": "repo.searchCode",
    "description": "Find existing test scripts/utilities by keyword or symbol.",
    "parameters": {
      "type": "object",
      "properties": {
        "query": { "type": "string", "description": "Keyword, path, or symbol to search for." },
        "limit": { "type": "number", "description": "Max results to return.", "default": 20 }
      },
      "required": ["query"]
    }
  },
  {
    "name": "flows.get",
    "description": "Fetch refined recorder flow by keyword. Returns canonical JSON with steps and selectors.",
    "parameters": {
      "type": "object",
      "properties": {
        "keyword": { "type": "string" },
        "strict": { "type": "boolean", "description": "If true, only exact matches." }
      },
      "required": ["keyword"]
    }
  },
  {
    "name": "flows.diff",
    "description": "Diff two flows and return a structured change set.",
    "parameters": {
      "type": "object",
      "properties": {
        "aFlowId": { "type": "string" },
        "bFlowId": { "type": "string" }
      },
      "required": ["aFlowId", "bFlowId"]
    }
  },
  {
    "name": "scripts.renderTemplate",
    "description": "Render a test file from a deterministic template for the chosen framework using the flow JSON.",
    "parameters": {
      "type": "object",
      "properties": {
        "framework": { "type": "string", "enum": ["playwright", "cypress", "selenium"] },
        "flowJson": { "type": "object" },
        "targetPath": { "type": "string", "description": "Desired path for the new test file." }
      },
      "required": ["framework", "flowJson"]
    }
  },
  {
    "name": "scripts.patchExisting",
    "description": "Apply an AST-safe patch to an existing file based on the flow diff.",
    "parameters": {
      "type": "object",
      "properties": {
        "path": { "type": "string" },
        "patchPlan": { "type": "object", "description": "LLM-generated plan; executor applies codemods/AST edits deterministically." }
      },
      "required": ["path", "patchPlan"]
    }
  },
  {
    "name": "runner.trial",
    "description": "Execute tests in container (headed/headless) and return artifacts.",
    "parameters": {
      "type": "object",
      "properties": {
        "path": { "type": "string", "description": "Path or glob to test(s)." },
        "mode": { "type": "string", "enum": ["headed", "headless"], "default": "headed" },
        "timeoutSec": { "type": "number", "default": 180 }
      },
      "required": ["path", "mode"]
    }
  },
  {
    "name": "vcs.openPR",
    "description": "Create a branch, commit changes, push, and open a PR.",
    "parameters": {
      "type": "object",
      "properties": {
        "branch": { "type": "string" },
        "title": { "type": "string" },
        "body": { "type": "string" },
        "files": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": { "path": { "type": "string" }, "content": { "type": "string" } },
            "required": ["path", "content"]
          }
        }
      },
      "required": ["branch", "title", "body", "files"]
    }
  }
]
```

---

### 3. Orchestrator Planning Prompt

```
**User keyword**: "{{keyword}}"

**Plan**

1. Call `repo.searchCode(query=keyword)`.
2. Call `flows.get(keyword)`.
3. If neither returns data → reply **"no relevant information available"**.
4. If both return data → compute `flows.diff(aFlowId=existing.flowId, bFlowId=refined.flowId)` and present a table: Step | Change | Old selector | New selector | Rationale. Ask for **patch** vs **regenerate** unless policy decides automatically.
5. If **regenerate** → `scripts.renderTemplate(framework, flowJson)`.
6. If **patch** → produce minimal `patchPlan` and call `scripts.patchExisting`.
7. `runner.trial(mode="headed")` on changed/new files → return logs + artifact links.
8. If trial **passes** → `vcs.openPR(...)` with PR body including diff summary and trial results. If **fails**, perform one localized patch attempt; otherwise stop and report.

**Reuse threshold**: prefer patch when overlap ≥ **0.6** and step types unchanged; otherwise regenerate.

**Output**: JSON summary `{decision, files, diffSummary?, trial: {ok, artifacts}, prUrl?}` plus a short human summary.
```

---

### 4. Deterministic Templates

#### Playwright (Handlebars example)

```handlebars
// tests/{{kebabCase flow.meta.name}}.spec.ts
import { test, expect } from '@playwright/test';

test.describe('{{flow.meta.name}}', () => {
  test('smoke', async ({ page }) => {
    {{#each flow.steps}}
    // {{this.action}} {{this.meta.note}}
    {{#if this.navigate}}await page.goto("{{this.navigate.url}}");{{/if}}
    {{#if this.click}}await page.locator(`{{this.selector.css}}`).click();{{/if}}
    {{#if this.fill}}await page.locator(`{{this.selector.css}}`).fill("{{this.fill.value}}");{{/if}}
    {{#if this.expect}}
      await expect(page.locator(`{{this.expect.selector.css}}`)).{{this.expect.matcher}}({{json this.expect.value}});
    {{/if}}
    {{/each}}
  });
});
```

Create analogous templates for Cypress and Selenium using the same deterministic pattern.

---

### 5. Pull Request Template (used in `vcs.openPR`)

```
**Title**: `test: {{keyword}} via flow {{flowId}} (trial: {{pass|fail}})`

**Body**

* **Keyword**: {{keyword}}
* **Flow**: {{flowId}} — framework: {{framework}}
* **Decision**: {{patch|regenerate}}
* **Flow Diff**: (table summarizing adds/removes/selector changes)
* **Files Changed**: (paths)
* **Trial Result**: {{pass|fail}}; artifacts: (links)
* **Risks**: selector brittleness, auth fixture changes
* **Follow-ups**: data-testids backlog, stabilize waits
```

---

### 6. Runner / CI Checklist

* Base image: `mcr.microsoft.com/playwright:focal` (or equivalent) with Node pinned.
* Install browsers: `npx playwright install --with-deps`.
* Headed mode in CI: `xvfb-run -a npx playwright test --headed`.
* Enable failure artifacts: screenshots, video retain-on-failure, HAR capture.
* Seed data deterministically and clean up after tests.
* Maintain login fixtures/state and auto-wait heuristics to prevent flake.

---

Store this document with the repo so anyone configuring the agent can follow a single source of truth.
