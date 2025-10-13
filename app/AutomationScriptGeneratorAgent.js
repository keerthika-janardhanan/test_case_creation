/**
 * AutomationScriptGeneratorAgent translates curated manual test cases into framework-compliant
 * automation assets. It analyses the target repository, reuses existing patterns from the vector
 * database, and coordinates user confirmations prior to persisting or pushing code.
 */

const crypto = require("crypto");
const path = require("path");

const { VectorDBManager } = require("./VectorDBManager");
const { GitHubIntegration } = require("./GitHubIntegration");

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

function slugify(text) {
    return String(text || "")
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-+|-+$/g, "") || "scenario";
}

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
    return new CodeTemplateFallback();
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
            temperature: options.temperature ?? 0.15,
            max_tokens: options.maxTokens ?? 1800,
            response_format: options.responseFormat,
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
        const content = json?.choices?.[0]?.message?.content;
        if (!content) {
            throw new Error("Azure OpenAI response missing message content.");
        }
        return content;
    }
}

class CodeTemplateFallback {
    async complete(messages) {
        const latest = messages[messages.length - 1]?.content || "";
        return JSON.stringify({
            locators: [],
            pages: [],
            tests: [
                {
                    path: "tests/generated.spec.ts",
                    content: `import { test } from '@playwright/test';

test.describe('Generated Scenario', () => {
  test('execute recorded steps', async ({ page }) => {
    // TODO: Implement automation based on manual steps.
    console.log(${JSON.stringify(latest)});
  });
});`,
                },
            ],
        });
    }
}

/**
 * Inspect repository files to determine the preferred automation language.
 * @param {string} repoPath
 * @returns {"playwright-ts"|"playwright-js"|"selenium-py"|"unknown"}
 */
function detectLanguage(repoPath) {
    const fs = require("fs");
    const patterns = [
        { type: "playwright-ts", test: (file) => file.endsWith(".ts") || file.endsWith(".tsx") },
        { type: "playwright-js", test: (file) => file.endsWith(".js") },
        { type: "selenium-py", test: (file) => file.endsWith(".py") },
    ];
    try {
        const files = fs.readdirSync(repoPath);
        for (const file of files) {
            const absolute = path.join(repoPath, file);
            const stat = fs.statSync(absolute);
            if (stat.isDirectory()) continue;
            for (const pattern of patterns) {
                if (pattern.test(file)) {
                    return pattern.type;
                }
            }
        }
    } catch (err) {
        // ignore
    }
    return "unknown";
}

class AutomationScriptGeneratorAgent {
    /**
     * @param {Object} [options]
     * @param {VectorDBManager} [options.vectorDbManager]
     * @param {GitHubIntegration} [options.gitIntegration]
     * @param {Object} [options.llmClient]
     */
    constructor(options = {}) {
        this.vectorDb = options.vectorDbManager || new VectorDBManager(options.vectorDbOptions);
        this.git = options.gitIntegration || new GitHubIntegration(options.gitOptions);
        this.llm = createLLMClient(options.llmClient);
        this.sessions = new Map();
    }

    /**
     * Initiate automation conversion from manual cases.
     * @param {Object} payload
     * @param {string} [payload.sessionId]
     * @param {Array<Object>} payload.manualTestCases
     * @param {string} [payload.keyword]
     * @param {Object} [payload.framework]
     * @returns {Promise<Object>}
     */
    async startSession(payload) {
        if (!payload.manualTestCases || payload.manualTestCases.length === 0) {
            throw new Error("AutomationScriptGeneratorAgent requires manualTestCases to begin.");
        }
        const sessionId = payload.sessionId || generateId();
        await this.git.ensureRepo();
        const frameworkStructure = await this.git.detectFrameworkStructure();
        const keyword = payload.keyword || payload.manualTestCases[0]?.title || "automation scenario";
        const slug = slugify(keyword);
        const recordedSequences = Array.isArray(payload.recordedSequences)
            ? payload.recordedSequences.filter((entry) => entry && Array.isArray(entry.steps) && entry.steps.length)
            : [];
        const recordedSteps = recordedSequences.flatMap((entry) => entry.steps);
        const vectorRecords = await this.vectorDb.querySimilarFlows(keyword, {
            topK: 6,
            requiredTypes: ["script", "script_scaffold", "locator", "page_object"],
        });
        const repoLanguage = detectLanguage(this.git.repoPath);
        const plan = this._buildPlan({
            slug,
            manualTestCases: payload.manualTestCases,
            frameworkStructure,
            repoLanguage,
            recordedCount: recordedSteps.length,
        });
        const existing = await this._findExistingAssets({ keyword, slug, manualTestCases: payload.manualTestCases });

        const session = {
            id: sessionId,
            stage: "planning",
            slug,
            keyword,
            manualTestCases: payload.manualTestCases,
            frameworkStructure,
            repoLanguage,
            plan,
            vectorRecords,
            existingAssets: existing,
            generatedPayload: null,
            branch: null,
            recordedSequences,
            recordedSteps,
        };
        this.sessions.set(sessionId, session);

        return {
            sessionId,
            status: "planning",
            plan,
            existingAssets: existing,
            frameworkStructure,
            repoLanguage,
            recordedStepCount: recordedSteps.length,
        };
    }

    _buildPlan(context) {
        const steps = [
            context.recordedCount && context.recordedCount > 0
                ? `Translate ${context.recordedCount} recorder-captured steps into an automation outline.`
                : "Review recorder data or capture a new session for sequencing.",
            "Analyse manual test cases and classify reusable actions.",
            "Inspect repository for existing locators, page objects, or specs.",
            "Design automation blueprint (fixtures, page methods, tests).",
            "Generate framework-compliant code for new or updated files.",
            "Prepare review summary highlighting changes.",
            "Stage files and await user approval to push.",
        ];
        return {
            createdAt: new Date().toISOString(),
            slug: context.slug,
            repoLanguage: context.repoLanguage,
            steps: steps.map((description, index) => ({
                id: `step-${index + 1}`,
                description,
                status: index === 0 ? "in-progress" : "pending",
            })),
        };
    }

    async _findExistingAssets(context) {
        const keywords = [
            context.keyword,
            ...context.manualTestCases.map((tc) => tc.title || "").filter(Boolean),
            slugify(context.slug),
        ]
            .map((value) => value.replace(/[^a-z0-9]+/gi, " ").trim())
            .filter((value) => value.length >= 4);
        const findings = await this.git.searchKeywords(keywords);
        const distinctFiles = new Map();
        for (const finding of findings) {
            if (!distinctFiles.has(finding.file)) {
                const content = await this.git.readFile(finding.file).catch(() => null);
                distinctFiles.set(finding.file, {
                    file: finding.file,
                    snippet: finding.line,
                    content,
                });
            }
        }
        return Array.from(distinctFiles.values());
    }

    async updatePlan(sessionId, payload) {
        const session = this.sessions.get(sessionId);
        if (!session) {
            throw new Error(`Automation session ${sessionId} not found.`);
        }
        if (payload.adjustments) {
            for (const adjustment of payload.adjustments) {
                const step = session.plan.steps.find((item) => item.id === adjustment.id);
                if (!step) continue;
                if (adjustment.description) {
                    step.description = adjustment.description;
                }
            }
        }
        if (payload.accept) {
            session.stage = "analysis";
            session.plan.steps[0].status = "completed";
            session.plan.steps[1].status = "in-progress";
            return {
                sessionId,
                status: "analysis",
                plan: session.plan,
                existingAssets: session.existingAssets,
            };
        }
        return {
            sessionId,
            status: session.stage,
            plan: session.plan,
        };
    }

    /**
     * After plan acceptance, perform detailed framework analysis and prepare blueprint preview.
     * @param {string} sessionId
     * @returns {Promise<Object>}
     */
    async prepareBlueprint(sessionId) {
        const session = this.sessions.get(sessionId);
        if (!session) {
            throw new Error(`Automation session ${sessionId} not found.`);
        }
        if (session.stage !== "analysis") {
            throw new Error(`Session ${sessionId} is not ready for blueprint generation.`);
        }
        const blueprint = this._buildBlueprint(session);
        session.blueprint = blueprint;
        session.stage = "awaiting-blueprint-confirmation";
        session.plan.steps[1].status = "completed";
        session.plan.steps[2].status = "in-progress";
        return {
            sessionId,
            status: session.stage,
            blueprint,
        };
    }

    _buildBlueprint(session) {
        const manualCases = session.manualTestCases;
        const actions = [];
        for (const testCase of manualCases) {
            const category = testCase.category || "positive";
            const steps = Array.isArray(testCase.steps) ? testCase.steps : [];
            steps.forEach((step, index) => {
                actions.push({
                    caseTitle: testCase.title,
                    category,
                    sequence: index + 1,
                    text: typeof step === "string" ? step : step.text || JSON.stringify(step),
                });
            });
        }
        const recordedActions = (session.recordedSequences || []).flatMap((sequence) =>
            sequence.steps.map((step) => ({
                sessionId: sequence.sessionId,
                sequence: step.sequence,
                summary: step.summary,
                locator: step.locator,
                actionType: step.actionType,
            }))
        );
        return {
            summary: `Generate automation for ${manualCases.length} manual cases across categories: ${[
                ...new Set(manualCases.map((tc) => tc.category || "positive")),
            ].join(", ")}.`,
            suggestedFiles: this._suggestFileLayout(session),
            actions,
            recordedActions,
            recordedStepCount: recordedActions.length,
        };
    }

    _suggestFileLayout(session) {
        const baseSlug = session.slug;
        const structure = session.frameworkStructure;
        const layout = [];
        if (structure.locators) {
            layout.push({
                type: "locator",
                path: path.join(structure.locators, `${baseSlug}.ts`),
            });
        }
        if (structure.pages) {
            const ext = session.repoLanguage === "selenium-py" ? ".py" : ".ts";
            layout.push({
                type: "page",
                path: path.join(structure.pages, `${capitalize(baseSlug)}Page${ext}`),
            });
        }
        if (structure.specs) {
            const ext =
                session.repoLanguage === "selenium-py" ? ".py" : session.repoLanguage === "playwright-js" ? ".spec.js" : ".spec.ts";
            layout.push({
                type: "test",
                path: path.join(structure.specs, `${baseSlug}${ext}`),
            });
        }
        return layout;
    }

    /**
     * Confirm blueprint before full code generation.
     * @param {string} sessionId
     * @param {Object} payload
     * @returns {Promise<Object>}
     */
    async confirmBlueprint(sessionId, payload = {}) {
        const session = this.sessions.get(sessionId);
        if (!session) {
            throw new Error(`Automation session ${sessionId} not found.`);
        }
        if (payload.adjustments) {
            session.blueprint.suggestedFiles = payload.adjustments.suggestedFiles || session.blueprint.suggestedFiles;
        }
        if (payload.accept) {
            session.stage = "generating";
            session.plan.steps[2].status = "completed";
            session.plan.steps[3].status = "in-progress";
            return {
                sessionId,
                status: session.stage,
            };
        }
        return {
            sessionId,
            status: session.stage,
            blueprint: session.blueprint,
        };
    }

    /**
     * Generate automation code payload based on approved blueprint.
     * @param {string} sessionId
     * @returns {Promise<Object>}
     */
    async generateCode(sessionId) {
        const session = this.sessions.get(sessionId);
        if (!session) {
            throw new Error(`Automation session ${sessionId} not found.`);
        }
        if (session.stage !== "generating") {
            throw new Error(`Session ${sessionId} is not ready for code generation.`);
        }
        const payload = await this._invokeCodeGeneration(session);
        session.generatedPayload = payload;
        session.stage = "awaiting-review";
        session.plan.steps[3].status = "completed";
        session.plan.steps[4].status = "in-progress";
        return {
            sessionId,
            status: session.stage,
            generated: payload,
        };
    }

    async _invokeCodeGeneration(session) {
        const blueprintSummary = session.blueprint.summary;
        const fileDescriptors = session.blueprint.suggestedFiles;
        const manualCases = session.manualTestCases;
        const recordedActions =
            session.blueprint.recordedActions && session.blueprint.recordedActions.length
                ? session.blueprint.recordedActions
                : (session.recordedSequences || []).flatMap((sequence) =>
                      sequence.steps.map((step) => ({
                          sessionId: sequence.sessionId,
                          sequence: step.sequence,
                          summary: step.summary,
                          locator: step.locator,
                          actionType: step.actionType,
                      }))
                  );
        const prompt = [
            {
                role: "system",
                content: "You convert manual QA cases into production-ready automation assets following repository conventions.",
            },
            {
                role: "user",
                content: JSON.stringify({
                    blueprintSummary,
                    fileDescriptors,
                    manualCases,
                    recordedActions,
                    recordedSessions: (session.recordedSequences || []).map((entry) => entry.sessionId),
                    repoLanguage: session.repoLanguage,
                }),
            },
        ];
        let response;
        try {
            response = await this.llm.complete(prompt, {
                maxTokens: 2200,
                responseFormat: { type: "json_object" },
            });
        } catch (err) {
            response = await new CodeTemplateFallback().complete(prompt);
        }
        let parsed;
        try {
            parsed = JSON.parse(response);
        } catch (err) {
            parsed = JSON.parse(await new CodeTemplateFallback().complete(prompt));
        }
        const files = []
            .concat(parsed.locators || [])
            .concat(parsed.pages || [])
            .concat(parsed.tests || []);
        return {
            files,
            metadata: {
                repoLanguage: session.repoLanguage,
                slug: session.slug,
                recordedStepCount: recordedActions.length,
            },
        };
    }

    /**
     * Persist generated files to the repository.
     * @param {string} sessionId
     * @returns {Promise<Object>}
     */
    async writeFiles(sessionId) {
        const session = this.sessions.get(sessionId);
        if (!session) {
            throw new Error(`Automation session ${sessionId} not found.`);
        }
        if (!session.generatedPayload) {
            throw new Error(`Session ${sessionId} has no generated payload to write.`);
        }
        const written = [];
        for (const file of session.generatedPayload.files) {
            await this.git.writeFile(file.path, file.content);
            written.push(file.path);
        }
        session.stage = "ready-for-push";
        session.plan.steps[4].status = "completed";
        session.plan.steps[5].status = "in-progress";
        return {
            sessionId,
            status: session.stage,
            writtenFiles: written,
        };
    }

    /**
     * Stage, commit, and push generated code after user confirmation.
     * @param {string} sessionId
     * @param {Object} options
     * @param {string} options.branch
     * @param {string} options.commitMessage
     * @returns {Promise<Object>}
     */
    async pushToGitHub(sessionId, options) {
        const session = this.sessions.get(sessionId);
        if (!session) {
            throw new Error(`Automation session ${sessionId} not found.`);
        }
        if (session.stage !== "ready-for-push") {
            throw new Error(`Session ${sessionId} is not ready for push.`);
        }
        const branch = options.branch || `automation/${session.slug}`;
        await this.git.checkoutBranch(branch, this.git.defaultBranch);
        await this.git.stageFiles(session.generatedPayload.files.map((file) => file.path));
        await this.git.commit(options.commitMessage || `Add automation for ${session.keyword}`);
        await this.git.push(branch, { setUpstream: true });
        session.stage = "completed";
        session.plan.steps[5].status = "completed";
        return {
            sessionId,
            status: "completed",
            branch,
        };
    }
}

function capitalize(value) {
    const text = String(value || "");
    if (!text) {
        return "";
    }
    return text.charAt(0).toUpperCase() + text.slice(1);
}

module.exports = {
    AutomationScriptGeneratorAgent,
};
