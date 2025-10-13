/**
 * ManualTestGeneratorAgent orchestrates semantic retrieval and LLM-driven synthesis
 * to produce granular manual test cases enriched with UI recorder context. The agent
 * supports keyword prompts, existing manual cases, and uploaded artefacts, and keeps
 * the workflow interactive so that users can adjust plans before finalisation.
 */

const crypto = require("crypto");
const path = require("path");
const fs = require("fs");

const { VectorDBManager } = require("./VectorDBManager");

/**
 * Generate UUID v4 using Node's crypto module while providing a fallback for older runtimes.
 * @returns {string}
 */
function generateId() {
    if (crypto.randomUUID) {
        return crypto.randomUUID();
    }
    return (
        Date.now().toString(16) +
        Math.random().toString(16).slice(2, 10) +
        Math.random().toString(16).slice(2, 10)
    );
}

/**
 * Create a lightweight LLM client that targets Azure OpenAI when configuration is available.
 * Falls back to a deterministic heuristic generator when credentials are missing, ensuring
 * offline usability during development.
 */
function createLLMClient(customClient) {
    if (customClient) {
        return customClient;
    }
    const endpoint = process.env.AZURE_OPENAI_ENDPOINT;
    const deployment = process.env.AZURE_OPENAI_DEPLOYMENT;
    const apiKey = process.env.AZURE_OPENAI_KEY;
    const apiVersion = process.env.AZURE_OPENAI_API_VERSION || process.env.OPENAI_API_VERSION || "2024-02-15-preview";

    if (endpoint && deployment && apiKey && typeof fetch === "function") {
        return new AzureChatCompletionClient({ endpoint, deployment, apiKey, apiVersion });
    }
    return new DeterministicFallbackLLM();
}

class AzureChatCompletionClient {
    constructor(options) {
        this.endpoint = options.endpoint.replace(/\/$/, "");
        this.deployment = options.deployment;
        this.apiKey = options.apiKey;
        this.apiVersion = options.apiVersion;
    }

    async complete(messages, options = {}) {
        const url = `${this.endpoint}/openai/deployments/${this.deployment}/chat/completions?api-version=${this.apiVersion}`;
        const body = {
            messages,
            temperature: options.temperature ?? 0.2,
            max_tokens: options.maxTokens ?? 1200,
        };
        const response = await fetch(url, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "api-key": this.apiKey,
            },
            body: JSON.stringify(body),
        });

        if (!response.ok) {
            const detail = await response.text();
            throw new Error(`Azure OpenAI request failed with status ${response.status}: ${detail}`);
        }

        const json = await response.json();
        const choice = json?.choices?.[0]?.message?.content;
        if (!choice) {
            throw new Error("Azure OpenAI response missing message content.");
        }
        return choice;
    }
}

/**
 * Deterministic fallback "LLM" to support local development without credentials. It uses the
 * retrieved context to craft structured manual steps.
 */
class DeterministicFallbackLLM {
    async complete(messages, options = {}) {
        const latest = messages[messages.length - 1];
        const context = latest?.content || "";
        const lines = context.split("\n").filter((line) => line.trim());
        const steps = lines.slice(0, 8).map((line, index) => `Step ${index + 1}: ${line.trim()}`);
        if (steps.length === 0) {
            steps.push("Step 1: Review the available UI recording steps and define a baseline scenario.");
            steps.push("Step 2: Document field-level actions with expected results.");
        }
        return steps.join("\n");
    }
}

const ACTION_VERBS = {
    focus: "Focus on",
    click: "Click",
    input: "Enter",
    change: "Select",
    hover: "Hover over",
    press: "Press",
    check: "Enable",
    uncheck: "Disable",
};

function limitText(value, max = 80) {
    if (!value) return "";
    const trimmed = String(value).trim();
    if (trimmed.length <= max) {
        return trimmed;
    }
    return `${trimmed.slice(0, max - 1)}…`;
}

function pickFirst(...values) {
    for (const value of values) {
        if (Array.isArray(value)) {
            const found = value.find((item) => item && String(item).trim());
            if (found) return String(found).trim();
        } else if (value && String(value).trim()) {
            return String(value).trim();
        }
    }
    return "";
}

function deriveElementLabel(element = {}) {
    const priorSibling = element.siblings?.previous?.text;
    const aria = element.ariaLabel || element.ariaLabelledBy;
    const label = pickFirst(
        priorSibling,
        aria,
        element.placeholder,
        element.text,
        element.title,
        element.name,
        element.nearestHeading,
        element.id
    );
    return limitText(label);
}

function deriveControlType(element = {}, actionType = "") {
    const tag = String(element.tagName || "").toLowerCase();
    const role = String(element.role || "");
    if (role.includes("button") || tag === "button") return "button";
    if (role.includes("link") || tag === "a") return "link";
    if (role.includes("checkbox") || element.type === "checkbox") return "checkbox";
    if (role.includes("radio") || element.type === "radio") return "radio option";
    if (role.includes("combobox") || element.type === "select-one" || tag === "select") return "dropdown";
    if (tag === "input" && (element.type === "password" || element.type === "email")) return `${element.type} field`;
    if (tag === "input" || tag === "textarea") return "input field";
    if (tag === "label") return "label";
    if (tag === "oj-button") return "oracle button";
    if (actionType === "hover") return "UI element";
    return tag || "element";
}

function buildLocator(element = {}) {
    if (element.stableSelector) {
        return element.stableSelector;
    }
    if (element.id) {
        const tag = String(element.tagName || "element").toLowerCase();
        return `${tag}#${element.id}`;
    }
    if (element.dataAttributes && element.dataAttributes["data-testid"]) {
        return `[data-testid="${element.dataAttributes["data-testid"]}"]`;
    }
    if (element.name) {
        const tag = String(element.tagName || "element").toLowerCase();
        return `${tag}[name="${element.name}"]`;
    }
    if (element.xpath) {
        return limitText(element.xpath, 160);
    }
    return "";
}

function buildExpected(actionType, label, controlType) {
    const target = label || controlType || "element";
    switch (actionType) {
        case "input":
            return `Typed value is accepted in ${target} and displayed without validation errors.`;
        case "change":
            return `Selection for ${target} updates and downstream fields refresh if required.`;
        case "click":
            return `${target} responds (navigation or state change) as designed.`;
        case "focus":
            return `${target} receives focus and becomes ready for input.`;
        case "hover":
            return `${target} reveals any hover states or tooltips as applicable.`;
        case "check":
        case "uncheck":
            return `${target} reflects the updated checked state.`;
        default:
            return `Application reacts appropriately for ${target}.`;
    }
}

function buildSummary(actionType, controlType, label, locator, value) {
    const verb = ACTION_VERBS[actionType] || "Interact with";
    const labelSegment = label ? ` "${label}"` : "";
    const locatorSegment = locator ? ` (locator: ${locator})` : "";
    const valueSegment =
        value && (actionType === "input" || actionType === "change")
            ? ` with value "${value}"`
            : "";
    return `${verb} ${controlType}${labelSegment}${valueSegment}${locatorSegment}`.trim();
}

function summariseRecorderAction(action, index) {
    const actionType = String(action?.action || action?.type || "interaction").toLowerCase();
    const element = action?.element || {};
    const controlType = deriveControlType(element, actionType);
    const label = deriveElementLabel(element);
    const locator = buildLocator(element);
    const valueMasked = element.valueMasked || null;
    const rawValue = element.value || action?.extra?.value || null;
    const displayValue = valueMasked || rawValue || null;

    return {
        sequence: index + 1,
        id: action?.actionId || `A-${String(index + 1).padStart(3, "0")}`,
        actionType,
        summary: buildSummary(actionType, controlType, label, locator, displayValue),
        locator,
        label,
        controlType,
        expected: buildExpected(actionType, label, controlType),
        value: rawValue,
        valueMasked,
        pageUrl: action?.pageUrl || null,
        pageTitle: action?.pageTitle || null,
        nearestHeading: element?.nearestHeading || null,
        screenshot: action?.extra?.screenshot || null,
        testData:
            displayValue && (actionType === "input" || actionType === "change")
                ? {
                      field: label || controlType || locator || `step_${index + 1}`,
                      value: rawValue,
                      masked: valueMasked,
                  }
                : null,
        rawAction: action,
    };
}

/**
 * Simplified accessor for the recorder directory that keeps responsibilities isolated from
 * the manual test generator logic.
 */
class UIRecorderBridge {
    /**
     * @param {Object} options
     * @param {string} options.recordingsDir
     */
    constructor(options = {}) {
        this.recordingsDir =
            options.recordingsDir ||
            path.resolve(__dirname, "../recordings");
    }

    _resolveSessionPath(sessionId) {
        return path.resolve(this.recordingsDir, sessionId);
    }

    async loadSession(sessionId) {
        const sessionDir = this._resolveSessionPath(sessionId);
        const metadataPath = path.join(sessionDir, "metadata.json");
        try {
            const buffer = await fs.promises.readFile(metadataPath);
            try {
                return JSON.parse(buffer.toString("utf8"));
            } catch (utf8Error) {
                return JSON.parse(buffer.toString("utf16le"));
            }
        } catch (err) {
            if (err.code === "ENOENT") {
                const fallback = path.resolve(this.recordingsDir, "..", "metadata_pretty.json");
                try {
                    const buffer = await fs.promises.readFile(fallback);
                    let parsed;
                    try {
                        parsed = JSON.parse(buffer.toString("utf8"));
                    } catch (utf8Error) {
                        parsed = JSON.parse(buffer.toString("utf16le"));
                    }
                    if (!sessionId || parsed?.session?.id === sessionId) {
                        return parsed;
                    }
                } catch {
                    return null;
                }
                return null;
            }
            throw err;
        }
    }

    async extractSteps(sessionId) {
        const data = await this.loadSession(sessionId);
        if (!data?.actions) {
            return [];
        }
        return data.actions.map((action, index) => summariseRecorderAction(action, index));
    }
}

/**
 * Normalise user-provided keywords to improve vector DB recall.
 * @param {string} keyword
 * @returns {string}
 */
function normaliseKeyword(keyword) {
    if (!keyword) {
        return "";
    }
    return keyword.trim().toLowerCase().replace(/\s+/g, " ");
}

/**
 * Project manual cases into a common structure regardless of their origin.
 * @param {Array<Object>|Object|string} input
 * @returns {Array<Object>}
 */
function normaliseManualCaseInput(input) {
    if (!input) {
        return [];
    }
    if (typeof input === "string") {
        return [
            {
                title: "Imported Case",
                steps: input.split("\n").map((line) => line.trim()).filter(Boolean),
            },
        ];
    }
    if (Array.isArray(input)) {
        return input;
    }
    return [input];
}

/**
 * Derive candidate negative and edge scenarios from retrieved metadata.
 * @param {Array<Object>} contextRecords
 * @returns {{negative: Array<string>, edge: Array<string>}}
 */
function deriveScenarioVariants(contextRecords) {
    const negative = new Set();
    const edge = new Set();
    for (const record of contextRecords) {
        const metadata = record.metadata || {};
        const tags = Array.isArray(metadata.tags) ? metadata.tags : String(metadata.tags || "").split(",");
        for (const tag of tags) {
            const token = tag.trim().toLowerCase();
            if (!token) continue;
            if (token.includes("negative") || token.includes("error")) {
                negative.add(token);
            } else if (token.includes("edge") || token.includes("boundary")) {
                edge.add(token);
            }
        }
    }
    return {
        negative: Array.from(negative),
        edge: Array.from(edge),
    };
}

/**
 * Convert structured steps to the textual output format required by the user.
 * @param {Array<Object>} steps
 * @returns {Array<string>}
 */
function renderSteps(steps) {
    return steps.map((step, index) => {
        const prefix = `Step ${index + 1}:`;
        return `${prefix} ${step.text}`;
    });
}

class ManualTestGeneratorAgent {
    /**
     * @param {Object} [options]
     * @param {VectorDBManager} [options.vectorDbManager]
     * @param {UIRecorderBridge} [options.uiRecorder]
     * @param {Object} [options.llmClient]
     */
    constructor(options = {}) {
        this.vectorDb = options.vectorDbManager || new VectorDBManager(options.vectorDbOptions);
        this.uiRecorder = options.uiRecorder || new UIRecorderBridge(options.recorderOptions);
        this.llm = createLLMClient(options.llmClient);
        this.sessions = new Map();
    }

    /**
     * Start a manual test generation session.
     * @param {Object} payload
     * @param {string} [payload.sessionId]
     * @param {string} [payload.keyword]
     * @param {Array<Object>|Object|string} [payload.manualTestCases]
     * @param {Array<Object>|Object|string} [payload.uploadedTestCases]
     * @param {string} [payload.description]
     * @returns {Promise<Object>}
     */
    async startSession(payload) {
        const sessionId = payload.sessionId || generateId();
        const keyword = normaliseKeyword(payload.keyword || payload.description || "ui flow");
        const manualReferences = normaliseManualCaseInput(payload.manualTestCases);
        const uploadReferences = normaliseManualCaseInput(payload.uploadedTestCases);

        const vectorRecords = await this.vectorDb.querySimilarFlows(keyword, {
            topK: 8,
            requiredTypes: ["ui_flow", "test_case", "manual_test_case"],
        });

        const recorderSessionIds = new Set();
        const candidateSessionId = payload.recorderSessionId || payload.recordingSessionId;
        if (candidateSessionId) {
            recorderSessionIds.add(candidateSessionId);
        }
        const candidateList = payload.recorderSessionIds || payload.recordingSessionIds || payload.recorderSessions;
        if (Array.isArray(candidateList)) {
            for (const item of candidateList) {
                if (item) {
                    recorderSessionIds.add(String(item));
                }
            }
        }
        for (const record of vectorRecords) {
            const meta = record.metadata || {};
            const sessionKey =
                meta.session_id ||
                meta.sessionId ||
                meta.session ||
                (meta.source === "recorder" ? meta.id : null);
            if (sessionKey) {
                recorderSessionIds.add(String(sessionKey));
            }
        }

        const recorderSequences = [];
        for (const id of recorderSessionIds) {
            try {
                const steps = await this.uiRecorder.extractSteps(id);
                if (steps.length) {
                    recorderSequences.push({
                        sessionId: id,
                        steps,
                    });
                }
            } catch (err) {
                // eslint-disable-next-line no-console
                console.warn(`Failed to load recorder session ${id}: ${err.message}`);
            }
        }

        // Fallback: attempt to use vector DB stored step summaries if no direct recorder session found.
        if (recorderSequences.length === 0) {
            for (const record of vectorRecords) {
                const steps = await this.vectorDb.resolveStepsFromRecord(record);
                if (steps.length) {
                    recorderSequences.push({
                        sessionId: record.metadata?.session_id || record.metadata?.sessionId || record.id,
                        steps: steps.map((step, index) => {
                            const raw = step.raw || {};
                            return summariseRecorderAction(
                                {
                                    action: raw.action || step.actionType || step.action || step.description,
                                    actionId: raw.actionId || step.id,
                                    element: raw.element || {},
                                    pageTitle: raw.pageTitle,
                                    pageUrl: raw.pageUrl,
                                    extra: raw.extra || {},
                                },
                                index
                            );
                        }),
                    });
                }
            }
        }

        const combinedRecordedSteps = recorderSequences.flatMap((entry) => entry.steps);
        const variants = deriveScenarioVariants(vectorRecords);
        const plan = await this._draftPlan({
            keyword,
            manualReferences,
            uploadReferences,
            vectorRecords,
            recorderSequences,
            combinedRecordedSteps,
            variants,
        });

        const session = {
            id: sessionId,
            stage: "planning",
            keyword,
            manualReferences,
            uploadReferences,
            vectorRecords,
            recorderSequences,
            combinedRecordedSteps,
            variants,
            plan,
            generated: null,
        };
        this.sessions.set(sessionId, session);

        return {
            sessionId,
            status: "planning",
            plan,
            suggestions: this._buildSuggestions(plan, variants, combinedRecordedSteps.length),
            contextSize: vectorRecords.length,
            recorderStepCount: combinedRecordedSteps.length,
        };
    }

    /**
     * Internal helper to synthesise a draft plan for positive/negative/edge scenarios.
     * @param {Object} context
     * @returns {Promise<Object>}
     * @private
     */
    async _draftPlan(context) {
        const recordedScenario =
            context.combinedRecordedSteps && context.combinedRecordedSteps.length
                ? this._buildRecordedScenario(context)
                : null;

        const positiveCase =
            recordedScenario ||
            (await this._generateScenario({
                title: "Positive Flow",
                keyword: context.keyword,
                emphasis: "successful happy-path execution",
                context,
            }));

        const negativeCase = await this._generateScenario({
            title: "Negative Flow",
            keyword: context.keyword,
            emphasis: context.variants.negative.join(", ") || "validation and failure paths",
            context,
        });
        const edgeCase = await this._generateScenario({
            title: "Edge Case Flow",
            keyword: context.keyword,
            emphasis: context.variants.edge.join(", ") || "boundary conditions",
            context,
        });

        const scenarios = [positiveCase, negativeCase, edgeCase];

        return {
            createdAt: new Date().toISOString(),
            scenarios,
        };
    }

    _buildRecordedScenario(context) {
        const recordedSteps = context.combinedRecordedSteps || [];
        return {
            title: "Recorded Happy Path",
            emphasis: "Follow the captured recorder sequence step-by-step.",
            recorded: true,
            sessionIds: (context.recorderSequences || []).map((entry) => entry.sessionId),
            recordedSteps,
            seedSteps: recordedSteps.map((step) => ({
                text: step.summary,
                locator: step.locator,
            })),
        };
    }

    /**
     * Compose scenario skeleton with contextual hints before final expansion.
     * @param {Object} options
     * @returns {Promise<Object>}
     * @private
     */
    async _generateScenario(options) {
        const recordedSummaries = (options.context.combinedRecordedSteps || [])
            .slice(0, 12)
            .map((step) => `${step.sequence}. ${step.summary}`);
        const manualSteps = [];
        for (const ref of options.context.manualReferences.concat(options.context.uploadReferences)) {
            const steps = Array.isArray(ref.steps) ? ref.steps : [];
            manualSteps.push(...steps.slice(0, 4));
        }
        const prompt = [
            {
                role: "system",
                content: "You design exhaustive manual QA scenarios with precise, verifiable steps.",
            },
            {
                role: "user",
                content: [
                    `Scenario focus: ${options.title} for "${options.keyword}".`,
                    `Special emphasis: ${options.emphasis}.`,
                    recordedSummaries.length
                        ? "Recorder sequence context:\n- " + recordedSummaries.join("\n- ")
                        : "Recorder sequence context: not available.",
                    manualSteps.length ? "Existing manual steps:\n- " + manualSteps.join("\n- ") : "No existing manual steps provided.",
                    "Produce 6-8 high-level manual steps with concise action + expected outcome phrasing. Reference recorder elements when possible.",
                ].join("\n"),
            },
        ];
        const draft = await this.llm.complete(prompt, { maxTokens: 600 });
        const steps = draft
            .split("\n")
            .map((line) => line.replace(/^\s*(\d+\.|-)\s*/, "").trim())
            .filter(Boolean)
            .map((text) => ({ text }));
        return {
            title: options.title,
            emphasis: options.emphasis,
            seedSteps: steps,
        };
    }

    /**
     * Build suggestions for the interactive confirmation prompt.
     * @param {Object} plan
     * @param {Object} variants
     * @returns {Array<string>}
     * @private
     */
    _buildSuggestions(plan, variants, recordedCount = 0) {
        const suggestions = [];
        if (recordedCount === 0) {
            suggestions.push("Attach a recorder session so the agent can ground steps on actual UI events.");
        } else if (recordedCount < 5) {
            suggestions.push("Capture a longer recorder session to cover more UI elements for the happy path.");
        }
        if (variants.negative.length === 0) {
            suggestions.push("Consider adding at least one negative scenario targeting invalid input or permission issues.");
        }
        if (variants.edge.length === 0) {
            suggestions.push("Add boundary data checks (e.g., maximum length, optional fields) to cover edge cases.");
        }
        const totalSteps = plan.scenarios.reduce((acc, scenario) => acc + scenario.seedSteps.length, 0);
        if (totalSteps < Math.max(12, recordedCount)) {
            suggestions.push("Expand the scenarios with more granular steps to reach comprehensive coverage.");
        }
        return suggestions;
    }

    /**
     * Update the draft plan with user feedback or acceptance.
     * @param {string} sessionId
     * @param {Object} payload
     * @param {boolean} [payload.accept]
     * @param {Array<Object>} [payload.adjustments]
     * @returns {Promise<Object>}
     */
    async updatePlan(sessionId, payload) {
        const session = this.sessions.get(sessionId);
        if (!session) {
            throw new Error(`Manual test session ${sessionId} not found.`);
        }
        if (payload.adjustments && Array.isArray(payload.adjustments)) {
            for (const adjustment of payload.adjustments) {
                const scenario = session.plan.scenarios.find((sc) => sc.title === adjustment.title);
                if (!scenario) continue;
                if (adjustment.emphasis) {
                    scenario.emphasis = adjustment.emphasis;
                }
                if (Array.isArray(adjustment.newSteps)) {
                    scenario.seedSteps = adjustment.newSteps.map((text) => ({ text }));
                }
            }
        }
        if (payload.accept) {
            session.stage = "pending-generation";
            return {
                sessionId,
                status: "pending-generation",
                plan: session.plan,
            };
        }
        return {
            sessionId,
            status: "planning",
            plan: session.plan,
        };
    }

    /**
     * Finalise manual test cases using the approved plan and enrichments.
     * @param {string} sessionId
     * @returns {Promise<Object>}
     */
    async generateFinalTestCases(sessionId) {
        const session = this.sessions.get(sessionId);
        if (!session) {
            throw new Error(`Manual test session ${sessionId} not found.`);
        }
        if (session.stage !== "pending-generation") {
            throw new Error(`Session ${sessionId} is not ready for final generation.`);
        }
        const enriched = await this._expandPlan(session);
        session.generated = enriched;
        session.stage = "completed";

        const recorderSessionsMeta = Array.from(
            new Set(
                enriched.testCases
                    .flatMap((tc) => (Array.isArray(tc.recorderSessions) ? tc.recorderSessions : []))
                    .filter(Boolean)
            )
        );

        await this.vectorDb.upsertDocument({
            source: "manual_test_generator",
            docId: sessionId,
            content: JSON.stringify(enriched.testCases, null, 2),
            metadata: {
                type: "manual_test_case",
                keyword: session.keyword,
                created_at: new Date().toISOString(),
                scenarios: enriched.testCases.map((tc) => tc.title),
                recorder_sessions: recorderSessionsMeta,
            },
        });

        return {
            sessionId,
            status: "completed",
            manualTestCases: enriched.testCases,
            exportText: enriched.exportText,
            recordedSessions: recorderSessionsMeta,
            recordedStepCount: session.combinedRecordedSteps.length,
        };
    }

    /**
     * Expand plan scenarios into structured manual test cases.
     * @param {Object} session
     * @returns {Promise<{testCases: Array<Object>, exportText: string}>}
     * @private
     */
    _convertRecordedScenarioToManual(scenario, session) {
        const recordedSteps =
            (scenario.recordedSteps && scenario.recordedSteps.length ? scenario.recordedSteps : session.combinedRecordedSteps) ||
            [];
        const sessionIds = Array.isArray(scenario.sessionIds) ? scenario.sessionIds : [];

        const steps = recordedSteps.map((step, index) => `Step ${index + 1}: ${step.summary}`);
        const expected = recordedSteps.map((step, index) => `Step ${index + 1}: ${step.expected}`);
        const testData = {};
        for (const step of recordedSteps) {
            if (step.testData) {
                const key = limitText(step.testData.field, 60) || `field_${step.sequence}`;
                testData[key] = step.testData.masked || step.testData.value;
            }
        }
        const locatorDetails = recordedSteps
            .filter((step) => step.locator)
            .map((step) => ({
                sequence: step.sequence,
                locator: step.locator,
                label: step.label,
                actionType: step.actionType,
            }));

        return {
            title: scenario.title,
            category: "positive",
            preconditions: [
                "Application under test is reachable.",
                "User has valid credentials with required permissions.",
                `Recorder sessions: ${sessionIds.length ? sessionIds.join(", ") : "not linked"}.`,
            ],
            steps,
            expectedResults: expected,
            testData,
            cleanup: ["Log out or revert test data if applicable."],
            locators: locatorDetails,
            recorderSessions: sessionIds,
        };
    }

    async _expandPlan(session) {
        const testCases = [];
        for (const scenario of session.plan.scenarios) {
            if (scenario.recorded) {
                testCases.push(this._convertRecordedScenarioToManual(scenario, session));
                continue;
            }

            const contextRows = scenario.seedSteps.map((step, index) => ({
                index: index + 1,
                text: step.text,
            }));
            const recordedSummaries = (session.combinedRecordedSteps || [])
                .slice(0, 10)
                .map((step) => `${step.sequence}. ${step.summary}`);
            const prompt = [
                {
                    role: "system",
                    content: "You are a senior QA analyst producing formal manual test cases.",
                },
                {
                    role: "user",
                    content: [
                        `Scenario: ${scenario.title} for ${session.keyword}`,
                        `Focus: ${scenario.emphasis}`,
                        "Recorded sequence context:",
                        ...(recordedSummaries.length ? recordedSummaries : ["No recorder context available."]),
                        "Seed steps:",
                        ...contextRows.map((row) => `- ${row.text}`),
                        "Return JSON with preconditions, steps (with locators if available), testData, expectedResults, and cleanup.",
                    ].join("\n"),
                },
            ];
            let content;
            try {
                content = await this.llm.complete(prompt, { maxTokens: 1200 });
            } catch (err) {
                // Fallback to deterministic format if LLM fails.
                content = JSON.stringify({
                    title: scenario.title,
                    preconditions: ["User has valid credentials.", "Application is reachable."],
                    steps: renderSteps(contextRows),
                    testData: {},
                    expectedResults: ["Application responds as described in each step."],
                    cleanup: ["Log out of the application."],
                });
            }
            let parsed;
            try {
                parsed = JSON.parse(content);
            } catch (err) {
                parsed = {
                    title: scenario.title,
                    preconditions: ["User has valid credentials.", "Application is reachable."],
                    steps: content.split("\n").filter(Boolean),
                    testData: {},
                    expectedResults: ["Application responds as described in each step."],
                    cleanup: ["Log out of the application."],
                };
            }
            if (!Array.isArray(parsed.steps)) {
                parsed.steps = renderSteps(contextRows);
            }
            parsed.title = parsed.title || scenario.title;
            parsed.category = scenario.title.toLowerCase().includes("negative")
                ? "negative"
                : scenario.title.toLowerCase().includes("edge")
                    ? "edge"
                    : "positive";
            testCases.push(parsed);
        }

        const exportLines = [];
        for (const testCase of testCases) {
            exportLines.push(`Test Case: ${testCase.title}`);
            if (Array.isArray(testCase.preconditions) && testCase.preconditions.length) {
                exportLines.push("Preconditions:");
                for (const item of testCase.preconditions) {
                    exportLines.push(`- ${item}`);
                }
            }
            if (Array.isArray(testCase.steps)) {
                exportLines.push("Steps:");
                for (const step of testCase.steps) {
                    exportLines.push(step);
                }
            }
            if (Array.isArray(testCase.expectedResults)) {
                exportLines.push("Expected Results:");
                for (const expected of testCase.expectedResults) {
                    exportLines.push(`- ${expected}`);
                }
            }
            if (Array.isArray(testCase.cleanup) && testCase.cleanup.length) {
                exportLines.push("Cleanup:");
                for (const cleanup of testCase.cleanup) {
                    exportLines.push(`- ${cleanup}`);
                }
            }
            if (Array.isArray(testCase.recorderSessions) && testCase.recorderSessions.length) {
                exportLines.push(`Recorder Sessions: ${testCase.recorderSessions.join(", ")}`);
            }
            exportLines.push("");
        }

        return {
            testCases,
            exportText: exportLines.join("\n"),
        };
    }
}

module.exports = {
    ManualTestGeneratorAgent,
    UIRecorderBridge,
};
