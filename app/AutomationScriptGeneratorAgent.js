/**
 * AutomationScriptGeneratorAgent translates curated manual test cases into framework-compliant
 * automation assets. It analyses the target repository, reuses existing patterns from the vector
 * database, and coordinates user confirmations prior to persisting or pushing code.
 */

const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

const { VectorDBManager } = require("./VectorDBManager");
const { GitHubIntegration } = require("./GitHubIntegration");
const toolSetup = require("../tools/agentic_tool_setup.json");
const { renderFrameworkTemplate } = require("./deterministic_templates");

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

const CACHE_DIR = path.join(__dirname, ".cache");
const REPO_INGEST_CACHE = path.join(CACHE_DIR, "repo_ingest_cache.json");
const SUPPORTED_REPO_EXTENSIONS = new Set([".ts", ".tsx", ".js", ".jsx", ".py"]);
const REPO_SKIP_DIRECTORIES = new Set([
    ".git",
    "node_modules",
    ".venv",
    "__pycache__",
    "dist",
    "build",
    ".cache",
]);
const MAX_INGEST_FILE_BYTES = 512 * 1024;
const fsp = fs.promises;

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
        this.toolSetup = toolSetup;
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
        try {
            await this.git.fetch();
        } catch (err) {
            // eslint-disable-next-line no-console
            console.warn("Failed to fetch latest repository updates:", err.message);
        }
        const frameworkStructure = await this.git.detectFrameworkStructure();
        const repoSyncStats = await this._ingestRepositorySnapshot(frameworkStructure);
        const keyword = payload.keyword || payload.manualTestCases[0]?.title || "automation scenario";
        const slug = slugify(keyword);
        const repoLanguage = detectLanguage(this.git.repoPath);
        const plan = this._buildPlan({
            slug,
            frameworkStructure,
            repoLanguage,
        });
        const repoMatches = await this._findExistingAssets({
            keyword,
            slug,
            manualTestCases: payload.manualTestCases,
        });
        const refinedFlow = await this._loadRefinedRecorderFlow(keyword, slug);
        const vectorFallback = refinedFlow ? [] : await this._loadVectorFallback(keyword);
        const warning =
            repoMatches.length === 0 && !refinedFlow && vectorFallback.length === 0
                ? "No information available"
                : null;
        const flowDiff = this._computeFlowDiff(refinedFlow, repoMatches);
        const hasRepoMatches = repoMatches.length > 0;
        const lowerKeyword = String(keyword || "").toLowerCase();
        const explicitRefinedRequest = lowerKeyword.includes("refined");
        let reuseRecommended = flowDiff ? flowDiff.overlap >= 0.6 : hasRepoMatches;
        if (explicitRefinedRequest) {
            reuseRecommended = false;
        }
        const needsGeneration = explicitRefinedRequest
            ? true
            : flowDiff
            ? !reuseRecommended
            : !hasRepoMatches && !refinedFlow;

        let defaultSelection = null;
        if (refinedFlow && (lowerKeyword.includes("refined") || !hasRepoMatches || !reuseRecommended)) {
            defaultSelection = "refined";
        } else if (hasRepoMatches) {
            defaultSelection = "repo";
        } else if (vectorFallback.length) {
            defaultSelection = "vector";
        }

        const session = {
            id: sessionId,
            stage: "planning",
            slug,
            keyword,
            manualTestCases: payload.manualTestCases,
            frameworkStructure,
            repoLanguage,
            plan,
            vectorRecords: vectorFallback,
            existingAssets: repoMatches,
            generatedPayload: null,
            branch: null,
            repoSync: repoSyncStats,
            contextSources: {
                repoMatches,
                refinedFlow,
                vectorMatches: vectorFallback,
                warning,
                selectedSource: defaultSelection,
                selectedSteps: [],
                needsGeneration,
                flowDiff,
                reuseRecommended,
                recommendedAction: reuseRecommended ? "patch" : "regenerate",
            },
        };
        if (session.plan.steps[0]) {
            session.plan.steps[0].status = "completed";
        }
        if (session.plan.steps[1]) {
            session.plan.steps[1].status = "completed";
        }
        if (session.plan.steps[2]) {
            session.plan.steps[2].status = "in-progress";
        }
        session.toolSetup = this.toolSetup;
        this.sessions.set(sessionId, session);

        if (defaultSelection) {
            try {
                await this._confirmContextAgainstRepo(session, defaultSelection);
            } catch (err) {
                // eslint-disable-next-line no-console
                console.warn(`Failed to auto-select ${defaultSelection} context:`, err.message);
            }
        }

        const contextState = session.contextSources;
        const resolvedFlowDiff = contextState?.flowDiff || flowDiff;

        return {
            sessionId,
            status: "planning",
            plan,
            existingAssets: repoMatches,
            frameworkStructure,
            repoLanguage,
            repoSync: repoSyncStats,
            refinedFlow,
            vectorFallback,
            vectorRecords: vectorFallback,
            warning,
            flowDiff: resolvedFlowDiff,
            toolSetup: this.toolSetup,
            context: contextState,
        };
    }

    _buildPlan(context) {
        const steps = [
            "Search repository for existing automation assets related to the keyword.",
            "Fetch refined recorder flow JSON for the keyword.",
            "Compare refined flow with existing scripts and present diff.",
            "Confirm patch versus regenerate strategy and prepare blueprint.",
            "Render deterministic automation assets or patch plan.",
            "Execute headed trial for affected specs and capture artifacts.",
            "Prepare review summary and PR body.",
            "Await approval to push branch and open pull request.",
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

    _normaliseKeywords(values) {
        return values
            .map((value) => String(value || "").replace(/[^a-z0-9]+/gi, " ").trim())
            .filter((value) => value.length >= 4);
    }

    _buildFilePreview(content, keywords) {
        if (!content) {
            return null;
        }
        const lines = content.split(/\r?\n/);
        if (!keywords || keywords.length === 0) {
            return lines.slice(0, 12).join("\n");
        }
        const loweredKeywords = keywords.map((kw) => kw.toLowerCase());
        let hitIndex = 0;
        for (let i = 0; i < lines.length; i += 1) {
            const lowerLine = lines[i].toLowerCase();
            if (loweredKeywords.some((kw) => lowerLine.includes(kw))) {
                hitIndex = i;
                break;
            }
        }
        const start = Math.max(0, hitIndex - 3);
        const end = Math.min(lines.length, hitIndex + 4);
        return lines.slice(start, end).join("\n");
    }

    async _resolveRepoFindings(findings, keywords, limit = 6, normalizedKeyword = "") {
        const distinctFiles = new Map();
        for (const finding of findings) {
            if (distinctFiles.size >= limit) {
                break;
            }
            if (!distinctFiles.has(finding.file)) {
                const content = await this.git.readFile(finding.file).catch(() => null);
                const preview = this._buildFilePreview(content, keywords);
                if (normalizedKeyword) {
                    const haystack = this._normaliseFlowKey(
                        `${finding.file} ${preview || ""}`.toLowerCase()
                    );
                    if (!haystack.includes(normalizedKeyword)) {
                        continue;
                    }
                }
                distinctFiles.set(finding.file, {
                    file: finding.file,
                    snippet: finding.line,
                    preview,
                    content,
                });
            }
        }
        return Array.from(distinctFiles.values());
    }

    async _findExistingAssets(context) {
        const keywords = this._normaliseKeywords([
            context.keyword,
            slugify(context.slug),
        ]);
        if (keywords.length === 0) {
            return [];
        }
        const normalizedKeyword = this._normaliseFlowKey(context.keyword || context.slug);
        const findings = await this.git.searchKeywords(keywords.slice(0, 8));
        return this._resolveRepoFindings(findings, keywords, 6, normalizedKeyword);
    }

    async _loadRepoCache() {
        try {
            await fsp.mkdir(CACHE_DIR, { recursive: true });
        } catch (err) {
            // ignore mkdir errors so long as directory exists or creation fails due to permissions
        }
        try {
            const raw = await fsp.readFile(REPO_INGEST_CACHE, "utf-8");
            const parsed = JSON.parse(raw);
            if (parsed && typeof parsed === "object" && parsed.files && typeof parsed.files === "object") {
                return parsed;
            }
        } catch (err) {
            // cache miss or invalid JSON, fall through to default
        }
        return { files: {} };
    }

    async _saveRepoCache(cache) {
        try {
            await fsp.mkdir(CACHE_DIR, { recursive: true });
            await fsp.writeFile(REPO_INGEST_CACHE, JSON.stringify(cache, null, 2), "utf-8");
        } catch (err) {
            // eslint-disable-next-line no-console
            console.error("Failed to persist repository ingest cache", err.message);
        }
    }

    _shouldSkipDirectory(entryName) {
        return REPO_SKIP_DIRECTORIES.has(entryName);
    }

    _shouldConsiderFile(entryName, stats) {
        if (!stats || stats.isDirectory()) {
            return false;
        }
        if (stats.size > MAX_INGEST_FILE_BYTES) {
            return false;
        }
        const ext = path.extname(entryName).toLowerCase();
        return SUPPORTED_REPO_EXTENSIONS.has(ext);
    }

    async _walkDirectory(root, accumulator) {
        let entries;
        try {
            entries = await fsp.readdir(root, { withFileTypes: true });
        } catch (err) {
            return;
        }
        for (const entry of entries) {
            const entryPath = path.join(root, entry.name);
            if (entry.isDirectory()) {
                if (this._shouldSkipDirectory(entry.name)) {
                    continue;
                }
                await this._walkDirectory(entryPath, accumulator);
                continue;
            }
            let stats;
            try {
                stats = await fsp.stat(entryPath);
            } catch (err) {
                continue;
            }
            if (!this._shouldConsiderFile(entry.name, stats)) {
                continue;
            }
            accumulator.push({
                absolute: entryPath,
                relative: path.relative(this.git.repoPath, entryPath),
                size: stats.size,
                mtimeMs: stats.mtimeMs,
            });
        }
    }

    async _collectRepoCandidates(frameworkStructure) {
        const repoRoot = this.git.repoPath;
        const directories = new Set();
        Object.values(frameworkStructure || {}).forEach((value) => {
            if (value) {
                directories.add(path.join(repoRoot, value));
            }
        });
        if (directories.size === 0) {
            ["tests", "specs", "e2e", "playwright"].forEach((fallback) => {
                directories.add(path.join(repoRoot, fallback));
            });
        }
        const files = [];
        for (const directory of directories) {
            await this._walkDirectory(directory, files);
        }
        return files;
    }

    async _ingestRepositorySnapshot(frameworkStructure) {
        const cache = await this._loadRepoCache();
        const cacheFiles = cache.files || {};
        const candidates = await this._collectRepoCandidates(frameworkStructure);
        let ingested = 0;
        let skipped = 0;

        for (const file of candidates) {
            const relativePath = file.relative.replace(/\\/g, "/");
            const docId = `repo::${relativePath}`;
            let content;
            try {
                content = await fsp.readFile(file.absolute, "utf-8");
            } catch (err) {
                skipped += 1;
                continue;
            }
            const hash = crypto.createHash("sha256").update(content).digest("hex");
            if (cacheFiles[docId] && cacheFiles[docId].hash === hash) {
                skipped += 1;
                continue;
            }
            try {
                await this.vectorDb.upsertDocument({
                    source: "repo_source",
                    docId,
                    content,
                    metadata: {
                        type: "repo_source",
                        path: relativePath,
                        hash,
                        size: file.size,
                        updated_at: new Date(file.mtimeMs).toISOString(),
                    },
                });
                cacheFiles[docId] = { hash, size: file.size, mtimeMs: file.mtimeMs };
                ingested += 1;
            } catch (err) {
                // eslint-disable-next-line no-console
                console.error(`Failed to upsert ${relativePath} into vector DB: ${err.message}`);
            }
        }

        cache.files = cacheFiles;
        await this._saveRepoCache(cache);
        return {
            scanned: candidates.length,
            ingested,
            skipped,
        };
    }

    _normaliseFlowKey(value) {
        return String(value || "").toLowerCase().replace(/[^a-z0-9]/g, "");
    }

    _summariseFlowSteps(steps, limit = 12) {
        if (!Array.isArray(steps) || steps.length === 0) {
            return [];
        }
        return steps.slice(0, limit).map((step, index) => {
            const action = step?.action || "";
            const navigation = step?.navigation || "";
            const locator =
                step?.locators?.playwright ||
                step?.locators?.stable ||
                step?.locators?.css ||
                step?.locators?.text ||
                step?.name ||
                step?.label ||
                "";
            const description = [action, navigation, locator].filter(Boolean).join(" | ");
            return `${index + 1}. ${description}`.trim();
        });
    }

    _primarySelector(step) {
        if (!step) {
            return "";
        }
        const locators = step.locators || {};
        const candidates = [
            locators.playwright,
            locators.stable,
            locators.css,
            locators.text,
            locators.xpath,
            locators.raw_xpath,
            locators.selector,
        ];
        for (const candidate of candidates) {
            if (typeof candidate === "string" && candidate.trim()) {
                return candidate.trim();
            }
        }
        if (typeof step.selector === "string" && step.selector.trim()) {
            return step.selector.trim();
        }
        return "";
    }

    _extractSelectorFromLine(line) {
        if (!line) {
            return "";
        }
        const trimmed = line.trim();
        const locatorMatch = trimmed.match(/locator\((`[^`]*`|'[^']*'|"[^"]*")\)/);
        if (locatorMatch) {
            return locatorMatch[1];
        }
        const getByMatch = trimmed.match(/page\.(getBy[A-Z][A-Za-z0-9]*)\((.+)\)/);
        if (getByMatch) {
            return `${getByMatch[1]}(${getByMatch[2]})`;
        }
        const expectMatch = trimmed.match(/expect\((.+?)\)/);
        if (expectMatch) {
            return expectMatch[1];
        }
        return trimmed;
    }

    _extractScriptSteps(content) {
        if (!content) {
            return [];
        }
        const lines = content.split(/\r?\n/);
        const steps = [];
        for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed || trimmed.startsWith("//") || !trimmed.includes("await page")) {
                continue;
            }
            const selector = this._extractSelectorFromLine(trimmed);
            const signature = this._normaliseFlowKey(`${selector} ${trimmed}`);
            steps.push({
                index: steps.length + 1,
                text: trimmed,
                selector,
                signature,
            });
        }
        return steps;
    }

    _computeFlowDiff(refinedFlow, repoMatches) {
        if (!refinedFlow || !Array.isArray(refinedFlow.steps) || refinedFlow.steps.length === 0) {
            return null;
        }
        const refinedSteps = this._filterAutomationSteps(refinedFlow.steps);
        const refinedEntries = refinedSteps.map((step, index) => {
            const selector = this._primarySelector(step);
            const key = this._normaliseFlowKey(`${step.action || ""} ${selector || step.navigation || ""}`);
            return {
                index: index + 1,
                action: step.action || "",
                navigation: step.navigation || "",
                selector,
                signature: key,
            };
        });
        const scriptAsset =
            (repoMatches || []).find((asset) => asset && asset.file && /\.(spec|test)\.(ts|js|tsx|jsx)$/.test(asset.file)) ||
            (repoMatches || []).find((asset) => asset && asset.file);
        const scriptSteps = scriptAsset ? this._extractScriptSteps(scriptAsset.content || "") : [];
        if (!scriptAsset || scriptSteps.length === 0) {
            const table = refinedEntries.map((entry) => ({
                step: entry.index,
                change: "added",
                oldSelector: "",
                newSelector: entry.selector || entry.navigation || entry.action,
                rationale: entry.navigation || entry.action || `Step ${entry.index} present only in refined flow`,
            }));
            return {
                overlap: 0,
                table: table.slice(0, 40),
                totals: {
                    refined: refinedEntries.length,
                    existing: scriptSteps.length,
                    matched: 0,
                    added: table.length,
                    removed: 0,
                },
                sampleExisting: [],
                sampleRefined: refinedEntries.slice(0, 5).map((entry) => entry.navigation || entry.action),
            };
        }
        const existingBySignature = new Map();
        for (const step of scriptSteps) {
            if (!existingBySignature.has(step.signature)) {
                existingBySignature.set(step.signature, step);
            }
        }
        let matched = 0;
        const diffRows = [];
        for (const entry of refinedEntries) {
            if (existingBySignature.has(entry.signature)) {
                matched += 1;
                existingBySignature.delete(entry.signature);
            } else {
                diffRows.push({
                    step: entry.index,
                    change: "added",
                    oldSelector: "",
                    newSelector: entry.selector || entry.navigation || entry.action,
                    rationale: entry.navigation || entry.action || `Step ${entry.index} present only in refined flow`,
                });
            }
        }
        for (const remaining of existingBySignature.values()) {
            diffRows.push({
                step: remaining.index,
                change: "removed",
                oldSelector: remaining.selector || remaining.text,
                newSelector: "",
                rationale: "Not present in refined recorder flow",
            });
        }
        const totalRefined = refinedEntries.length;
        const totalExisting = scriptSteps.length;
        const overlapDenominator = Math.max(totalRefined, totalExisting) || 1;
        const overlap = overlapDenominator ? matched / overlapDenominator : 0;
        return {
            overlap: Number(overlap.toFixed(2)),
            table: diffRows.slice(0, 40),
            totals: {
                refined: totalRefined,
                existing: totalExisting,
                matched,
                added: diffRows.filter((row) => row.change === "added").length,
                removed: diffRows.filter((row) => row.change === "removed").length,
            },
            sampleExisting: scriptSteps.slice(0, 5).map((step) => step.text),
            sampleRefined: refinedEntries.slice(0, 5).map((entry) => entry.navigation || entry.action),
        };
    }

    _filterAutomationSteps(steps) {
        if (!Array.isArray(steps)) {
            return [];
        }
        return steps.filter((step) => {
            const locators = step?.locators;
            if (!locators || typeof locators !== "object") {
                return false;
            }
            const candidate =
                [locators.playwright, locators.stable, locators.css, locators.xpath]
                    .find((value) => typeof value === "string" && value.trim().length > 0) ||
                null;
            return Boolean(candidate);
        });
    }

    _determineFramework(session) {
        const language = session.repoLanguage || "";
        if (language.startsWith("playwright")) {
            return "playwright";
        }
        if (language === "selenium-py") {
            return "selenium";
        }
        return "playwright";
    }

    _determineTestPath(session, framework) {
        const structure = session.frameworkStructure || {};
        const baseDir = structure.specs || structure.tests || "tests";
        if (framework === "selenium") {
            return path.join(baseDir, `${session.slug}.py`);
        }
        if (framework === "cypress") {
            return path.join(baseDir, `${session.slug}.cy.ts`);
        }
        return path.join(baseDir, `${session.slug}.spec.ts`);
    }

    _stepsContainKeyword(steps, normalizedKeyword) {
        if (!normalizedKeyword) {
            return true;
        }
        return steps.some((step) => {
            const textParts = [
                step?.action,
                step?.navigation,
                step?.name,
                step?.label,
                step?.expected,
            ].filter(Boolean);
            if (!textParts.length) {
                return false;
            }
            const normalised = this._normaliseFlowKey(textParts.join(" "));
            return normalised.includes(normalizedKeyword);
        });
    }

    async _loadRefinedRecorderFlow(keyword, slug) {
        const flowsDir = path.resolve(__dirname, "generated_flows");
        let entries;
        try {
            entries = await fsp.readdir(flowsDir);
        } catch (err) {
            return null;
        }
        const refinedFiles = await Promise.all(
            entries
                .filter((entry) => entry.endsWith(".refined.json"))
                .map(async (entry) => {
                    const absolute = path.join(flowsDir, entry);
                    try {
                        const stat = await fsp.stat(absolute);
                        return { absolute, entry, mtimeMs: stat.mtimeMs };
                    } catch (err) {
                        return null;
                    }
                })
        );
        const filtered = refinedFiles.filter(Boolean).sort((a, b) => b.mtimeMs - a.mtimeMs);
        if (filtered.length === 0) {
            return null;
        }
        const stopWords = new Set(["for", "from", "the", "a", "an", "and", "with", "via"]);
        const targetKeys = new Set();
        const pushTarget = (value) => {
            if (!value) {
                return;
            }
            const key = this._normaliseFlowKey(value);
            if (!key) {
                return;
            }
            targetKeys.add(key);

            const withoutGenerics = key.replace(/(refined|recorder|flow|script|test|automation|ui)+/g, "");
            if (withoutGenerics && withoutGenerics !== key) {
                targetKeys.add(withoutGenerics);
            }
            const withoutDigits = key.replace(/\d+/g, "");
            if (withoutDigits && withoutDigits !== key) {
                targetKeys.add(withoutDigits);
            }

            const wordish = String(value || "")
                .toLowerCase()
                .replace(/[^a-z0-9]+/g, " ")
                .split(" ")
                .filter(Boolean);
            for (const word of wordish) {
                if (stopWords.has(word)) {
                    continue;
                }
                const token = this._normaliseFlowKey(word);
                if (token && token.length >= 3) {
                    targetKeys.add(token);
                }
            }
            for (let i = 0; i < wordish.length - 1; i += 1) {
                if (stopWords.has(wordish[i]) || stopWords.has(wordish[i + 1])) {
                    continue;
                }
                const bigram = this._normaliseFlowKey(`${wordish[i]} ${wordish[i + 1]}`);
                if (bigram && bigram.length >= 5) {
                    targetKeys.add(bigram);
                }
            }
        };
        pushTarget(keyword);
        pushTarget(slug);
        if (keyword) {
            pushTarget(keyword.replace(/refined recorder flow/gi, ""));
            pushTarget(keyword.replace(/refined flow/gi, ""));
            pushTarget(keyword.replace(/recorder flow/gi, ""));
        }
        if (slug) {
            pushTarget(slug.replace(/-?(refined|flow|script|test|automation|ui)+$/gi, ""));
        }
        const targetKeyList = Array.from(targetKeys).filter(Boolean);
        const slugCandidates = new Set();
        const pushSlug = (value) => {
            if (!value) {
                return;
            }
            const slugValue = slugify(String(value));
            if (slugValue) {
                slugCandidates.add(slugValue);
            }
        };
        pushSlug(keyword);
        pushSlug(slug);
        if (keyword) {
            pushSlug(keyword.replace(/refined recorder flow/gi, ""));
            pushSlug(keyword.replace(/refined flow/gi, ""));
            pushSlug(keyword.replace(/recorder flow/gi, ""));
        }
        if (slug) {
            pushSlug(slug.replace(/-?(refined|flow|script|test|automation|ui)+$/gi, ""));
        }
        if (targetKeyList.length === 0) {
            return null;
        }
        const stepMatchKey =
            targetKeyList.find((key) => key.length >= 3 && !/(refined|recorder|flow|script|test|automation|ui)/.test(key)) ||
            targetKeyList.find((key) => key.length >= 3) ||
            targetKeyList.find((key) => key.length > 0) ||
            "";

        const candidateInfos = [];
        for (const candidate of filtered) {
            try {
                const raw = await fsp.readFile(candidate.absolute, "utf-8");
                const data = JSON.parse(raw);
                const flowName = data.flow_name || path.basename(candidate.entry, ".refined.json");
                const steps = Array.isArray(data.steps) ? this._filterAutomationSteps(data.steps) : [];
                if (!steps.length) {
                    continue;
                }
                const entrySlug = slugify(path.basename(candidate.entry, ".refined.json"));
                const flowSlug = slugify(flowName);
                const slugAligned = Array.from(slugCandidates).some((candidateSlug) => {
                    if (!candidateSlug) {
                        return false;
                    }
                    return (
                        candidateSlug === flowSlug ||
                        candidateSlug === entrySlug ||
                        candidateSlug.includes(flowSlug) ||
                        candidateSlug.includes(entrySlug) ||
                        flowSlug.includes(candidateSlug) ||
                        entrySlug.includes(candidateSlug)
                    );
                });
                if (!slugAligned && stepMatchKey && !this._stepsContainKeyword(steps, stepMatchKey)) {
                    continue;
                }
                const entryKeys = new Set();
                const pushEntryKey = (value) => {
                    if (!value) {
                        return;
                    }
                    const key = this._normaliseFlowKey(value);
                    if (!key) {
                        return;
                    }
                    entryKeys.add(key);
                    const noDigits = key.replace(/\d+/g, "");
                    if (noDigits && noDigits !== key) {
                        entryKeys.add(noDigits);
                    }
                };
                pushEntryKey(candidate.entry);
                const basename = path.basename(candidate.entry, ".refined.json");
                pushEntryKey(basename);
                basename.split(/[-_]/).forEach((part) => pushEntryKey(part));
                pushEntryKey(flowName);
                pushEntryKey(slugify(flowName));
                if (typeof data.flow_slug === "string") {
                    pushEntryKey(data.flow_slug);
                }
                let score = 0;
                for (const target of targetKeyList) {
                    if (!target) {
                        continue;
                    }
                    for (const key of entryKeys) {
                        if (!key) {
                            continue;
                        }
                        if (key.includes(target) || target.includes(key)) {
                            const overlap = Math.min(target.length, key.length);
                            if (overlap > score) {
                                score = overlap;
                            }
                        }
                    }
                }
                const preview = this._summariseFlowSteps(steps);
                candidateInfos.push({
                    candidate,
                    flowName,
                    steps,
                    elements: Array.isArray(data.elements) ? data.elements : [],
                    preview,
                    score,
                });
            } catch (err) {
                continue;
            }
        }
        if (candidateInfos.length === 0) {
            return null;
        }
        candidateInfos.sort((a, b) => {
            if (b.score !== a.score) {
                return b.score - a.score;
            }
            return b.candidate.mtimeMs - a.candidate.mtimeMs;
        });
        const best = candidateInfos[0];
        return {
            file: path.relative(process.cwd(), best.candidate.absolute),
            flowName: best.flowName,
            steps: best.steps,
            elements: best.elements,
            preview: best.preview,
        };
    }

    async _loadVectorFallback(keyword) {
        if (!keyword || !keyword.trim()) {
            return [];
        }
        const normalizedKey = this._normaliseFlowKey(keyword);
        const records = await this.vectorDb.querySimilarFlows(keyword, {
            topK: 5,
            requiredTypes: ["script", "script_scaffold", "automation_script", "repo_source", "locator", "page_object"],
        });
        const filtered = [];
        for (const record of records) {
            let parsed = null;
            try {
                parsed = JSON.parse(record.content);
            } catch (err) {
                // ignore parse errors; keep raw content
            }
            const metadata = record.metadata || {};
            const candidateTokens = [
                metadata.slug,
                metadata.keyword,
                metadata.flow_name,
                metadata.title,
                metadata.path,
                metadata.file,
            ]
                .filter(Boolean)
                .map((value) => this._normaliseFlowKey(String(value)));

            if (normalizedKey && candidateTokens.length > 0) {
                const matching = candidateTokens.some((token) => token && token.includes(normalizedKey));
                if (!matching) {
                    continue;
                }
            } else if (normalizedKey) {
                // If we have a keyword but no usable metadata, skip to avoid loose matches.
                continue;
            }

            const steps = Array.isArray(parsed?.steps) ? this._filterAutomationSteps(parsed.steps) : [];
            if (!steps.length) {
                continue;
            }
            if (!this._stepsContainKeyword(steps, normalizedKey)) {
                continue;
            }
            const preview = this._summariseFlowSteps(steps);
            filtered.push({
                id: record.id,
                metadata,
                steps,
                preview,
                content: record.content,
            });
        }
        return filtered;
    }

    async _confirmContextAgainstRepo(session, selectionOverride) {
        const context = session.contextSources || {};
        let selection = selectionOverride || context.selectedSource;
        if (!selection) {
            if (Array.isArray(context.repoMatches) && context.repoMatches.length) {
                selection = "repo";
            } else if (context.refinedFlow) {
                selection = "refined";
            } else if (Array.isArray(context.vectorMatches) && context.vectorMatches.length) {
                selection = "vector";
            } else {
                selection = "none";
            }
        }
        context.selectedSource = selection;
        let matches = Array.isArray(context.repoMatches) ? context.repoMatches : [];

        if (selection === "repo") {
            context.selectedSteps = [];
            if (context.refinedFlow) {
                const diff = this._computeFlowDiff(context.refinedFlow, matches);
                context.flowDiff = diff;
                context.reuseRecommended = diff ? diff.overlap >= 0.6 : false;
                context.recommendedAction = context.reuseRecommended ? "patch" : "regenerate";
            }
            context.needsGeneration = !(context.reuseRecommended && matches.length > 0);
            if (matches.length > 0) {
                context.warning = null;
            }
            session.contextSources = context;
            return {
                source: "repo",
                matches,
                needsGeneration: context.needsGeneration,
                flowDiff: context.flowDiff,
                recommendedAction: context.recommendedAction,
            };
        }

        if (selection === "refined" && context.refinedFlow) {
            const keywords = this._normaliseKeywords([
                session.keyword,
                context.refinedFlow.flowName,
                ...(context.refinedFlow.steps || []).slice(0, 6).map((step) => step.action || step.navigation || step.expected || ""),
            ]);
            const findings = keywords.length ? await this.git.searchKeywords(keywords.slice(0, 8)) : [];
            matches = await this._resolveRepoFindings(findings, keywords, 6);
            context.repoMatches = matches;
            context.selectedSteps = context.refinedFlow.steps || [];
            const diff = this._computeFlowDiff(context.refinedFlow, matches);
            context.flowDiff = diff;
            context.reuseRecommended = diff ? diff.overlap >= 0.6 : false;
            context.recommendedAction = context.reuseRecommended ? "patch" : "regenerate";
            context.needsGeneration = !context.reuseRecommended;
            if (context.selectedSteps.length > 0) {
                context.warning = null;
            }
            session.contextSources = context;
            return {
                source: "refined",
                matches,
                keywords,
                needsGeneration: context.needsGeneration,
                flowDiff: context.flowDiff,
                recommendedAction: context.recommendedAction,
            };
        }

        if (selection === "vector" && Array.isArray(context.vectorMatches) && context.vectorMatches.length) {
            const primary = context.vectorMatches[0];
            let keywords = this._normaliseKeywords([
                session.keyword,
                primary?.metadata?.keyword,
                primary?.metadata?.flow_name,
                primary?.metadata?.slug,
                primary?.metadata?.title,
            ]);
            const resolvedMatches = [];
            const metadataPath = primary?.metadata?.path || primary?.metadata?.file || null;
            if (metadataPath) {
                try {
                    const content = await this.git.readFile(metadataPath);
                    resolvedMatches.push({
                        file: metadataPath,
                        snippet: "",
                        preview: this._buildFilePreview(content, keywords),
                        content,
                    });
                } catch (err) {
                    // ignore read failures
                }
            }
            if (resolvedMatches.length === 0) {
                if (keywords.length === 0 && primary?.preview) {
                    keywords = this._normaliseKeywords([primary.preview]);
                }
                const findings = keywords.length ? await this.git.searchKeywords(keywords.slice(0, 8)) : [];
                matches = await this._resolveRepoFindings(findings, keywords, 6);
            } else {
                matches = resolvedMatches;
            }
            context.repoMatches = matches;
            context.selectedSteps = Array.isArray(primary?.steps) ? primary.steps : [];
            context.flowDiff = null;
            context.reuseRecommended = false;
            context.recommendedAction = "regenerate";
            context.needsGeneration = true;
            if (context.selectedSteps.length > 0 || matches.length > 0) {
                context.warning = null;
            }
            session.contextSources = context;
            return {
                source: "vector",
                matches,
                keywords,
                needsGeneration: context.needsGeneration,
                recommendedAction: context.recommendedAction,
            };
        }

        context.selectedSteps = [];
        context.needsGeneration = true;
        session.contextSources = context;
        return {
            source: selection,
            matches: [],
            needsGeneration: true,
        };
    }

    async updatePlan(sessionId, payload) {
        const session = this.sessions.get(sessionId);
        if (!session) {
            throw new Error(`Automation session ${sessionId} not found.`);
        }
        const contextState = session.contextSources || {};
        const hasContext =
            (Array.isArray(contextState.repoMatches) && contextState.repoMatches.length > 0) ||
            Boolean(contextState.refinedFlow) ||
            (Array.isArray(contextState.vectorMatches) && contextState.vectorMatches.length > 0);
        if (!hasContext) {
            if (payload.accept) {
                throw new Error(
                    "No automation assets found in repository, refined recorder flows, or vector DB. Please ingest a flow before continuing."
                );
            }
            return {
                sessionId,
                status: session.stage,
                plan: session.plan,
                context: contextState,
                warning: contextState.warning || "No automation assets available for this keyword.",
            };
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
        let repoConfirmation = null;
        if (session.stage === "planning") {
            if (payload.selection) {
                repoConfirmation = await this._confirmContextAgainstRepo(session, payload.selection);
                session.existingAssets = session.contextSources.repoMatches || [];
            }
            if (payload.accept) {
                if (!repoConfirmation) {
                    repoConfirmation = await this._confirmContextAgainstRepo(session);
                    session.existingAssets = session.contextSources.repoMatches || [];
                }
                const confirmedSource = session.contextSources?.selectedSource;
                const confirmedSteps = Array.isArray(session.contextSources?.selectedSteps)
                    ? this._filterAutomationSteps(session.contextSources.selectedSteps)
                    : [];
                const hasRepoReuse =
                    confirmedSource === "repo" && Array.isArray(session.contextSources?.repoMatches)
                        ? session.contextSources.repoMatches.length > 0
                        : false;
                if (
                    confirmedSource === "none" ||
                    (!hasRepoReuse && confirmedSteps.length === 0)
                ) {
                    throw new Error(
                        "No automation flow with actionable locators was found. Please ingest a recorder flow or confirm an existing repository script before continuing."
                    );
                }
                session.contextSources.selectedSteps = confirmedSteps;
                session.stage = "analysis";
                if (session.plan.steps[2]) {
                    session.plan.steps[2].status = "completed";
                }
                if (session.plan.steps[3]) {
                    session.plan.steps[3].status = "in-progress";
                }
                return {
                    sessionId,
                    status: "analysis",
                    plan: session.plan,
                    context: session.contextSources,
                    repoConfirmation,
                    existingAssets: session.existingAssets,
                };
            }
            return {
                sessionId,
                status: session.stage,
                plan: session.plan,
                context: session.contextSources,
                repoConfirmation,
            };
        }
        return {
            sessionId,
            status: session.stage,
            plan: session.plan,
            context: session.contextSources,
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
        const context = session.contextSources || {};
        if (
            context &&
            context.selectedSource === "repo" &&
            context.needsGeneration === false &&
            (!Array.isArray(context.selectedSteps) || context.selectedSteps.length === 0)
        ) {
            throw new Error(
                "Existing automation was found in the repository. Blueprint generation is not required."
            );
        }
        const blueprint = this._buildBlueprint(session);
        session.blueprint = blueprint;
        session.stage = "awaiting-blueprint-confirmation";
        if (session.plan.steps[3]) {
            session.plan.steps[3].status = "completed";
        }
        if (session.plan.steps[4]) {
            session.plan.steps[4].status = "in-progress";
        }
        return {
            sessionId,
            status: session.stage,
            blueprint,
        };
    }

    _buildBlueprint(session) {
        const context = session.contextSources || {};
        const selectedSteps = this._filterAutomationSteps(
            Array.isArray(context.selectedSteps) ? context.selectedSteps : []
        );
        if (!selectedSteps.length) {
            throw new Error(
                "No flow steps were found in the selected source. Cannot prepare automation blueprint."
            );
        }
        const sourceLabel =
            context.selectedSource === "refined"
                ? context.refinedFlow?.flowName || session.keyword
                : context.selectedSource === "vector"
                ? context.vectorMatches?.[0]?.metadata?.title ||
                  context.vectorMatches?.[0]?.metadata?.flow_name ||
                  session.keyword
                : session.keyword;

        const actions = selectedSteps.map((step, index) => {
            const text =
                step?.navigation ||
                step?.action ||
                step?.summary ||
                step?.name ||
                step?.label ||
                (typeof step === "string" ? step : JSON.stringify(step));
            return {
                caseTitle: `${sourceLabel} flow`,
                category: context.selectedSource || "context",
                sequence: index + 1,
                text,
            };
        });

        const recordedActions = selectedSteps.map((step, index) => {
            const locator =
                step?.locators?.playwright ||
                step?.locators?.stable ||
                step?.locators?.css ||
                step?.locators?.text ||
                step?.locator ||
                "";
            const summaryParts = [
                step?.action,
                step?.navigation,
                step?.name,
                step?.label,
                typeof locator === "string" ? locator : "",
            ].filter(Boolean);
            return {
                sessionId: context.selectedSource || "context",
                sequence: index + 1,
                summary:
                    summaryParts.length > 0
                        ? summaryParts.join(" | ")
                        : typeof step === "string"
                        ? step
                        : JSON.stringify(step),
                locator,
                actionType: step?.action || step?.actionType || "context-step",
            };
        });

        return {
            summary: `Generate automation from the ${sourceLabel} flow (${context.selectedSource || "context"}).`,
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
            if (session.plan.steps[4]) {
                session.plan.steps[4].status = "completed";
            }
            if (session.plan.steps[5]) {
                session.plan.steps[5].status = "in-progress";
            }
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
        const canReuseExisting =
            session.contextSources &&
            session.contextSources.needsGeneration === false &&
            Array.isArray(session.existingAssets) &&
            session.existingAssets.length > 0;
        if (!session.blueprint && !canReuseExisting) {
            throw new Error("Automation blueprint not prepared. Generate a blueprint before requesting code.");
        }
        if (canReuseExisting) {
            const reusePayload = {
                files: [],
                metadata: {
                    repoLanguage: session.repoLanguage,
                    slug: session.slug,
                    reuseSource: session.contextSources?.selectedSource || "repository",
                    reusedFiles: session.existingAssets.map((asset) => asset.file),
                    recordedStepCount: session.blueprint?.recordedStepCount ?? 0,
                },
            };
            session.generatedPayload = reusePayload;
            session.stage = "awaiting-review";
            if (session.plan.steps[4]) {
                session.plan.steps[4].status = "completed";
            }
            if (session.plan.steps[5]) {
                session.plan.steps[5].status = "in-progress";
            }
            return {
                sessionId,
                status: session.stage,
                generated: reusePayload,
                reuse: session.existingAssets,
            };
        }
        const payload = await this._invokeCodeGeneration(session);
        session.generatedPayload = payload;
        session.stage = "awaiting-review";
        if (session.plan.steps[4]) {
            session.plan.steps[4].status = "completed";
        }
        if (session.plan.steps[5]) {
            session.plan.steps[5].status = "in-progress";
        }
        return {
            sessionId,
            status: session.stage,
            generated: payload,
        };
    }

    async _invokeCodeGeneration(session) {
        const context = session.contextSources || {};
        const selectedSteps = this._filterAutomationSteps(
            Array.isArray(context.selectedSteps) ? context.selectedSteps : []
        );
        if (!selectedSteps.length) {
            throw new Error("No flow steps available for code generation. Aborting.");
        }
        const framework = this._determineFramework(session);
        const flowName =
            (context.selectedSource === "refined" && context.refinedFlow?.flowName) ||
            context.refinedFlow?.flowName ||
            session.keyword ||
            session.slug;
        const targetPath = this._determineTestPath(session, framework);
        const files = renderFrameworkTemplate({
            framework,
            flowName,
            slug: session.slug,
            steps: selectedSteps,
            targetPath,
            suggestedFiles: session.blueprint?.suggestedFiles || [],
        });
        return {
            files,
            metadata: {
                repoLanguage: session.repoLanguage,
                slug: session.slug,
                flowSource: context.selectedSource || "context",
                recordedStepCount: selectedSteps.length,
                framework,
                template: "deterministic",
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
        if (session.plan.steps[5] && session.plan.steps[5].status !== "completed") {
            session.plan.steps[5].status = "completed";
        }
        if (session.plan.steps[6]) {
            session.plan.steps[6].status = "in-progress";
        }
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
        if (session.plan.steps[6]) {
            session.plan.steps[6].status = "completed";
        }
        if (session.plan.steps[7]) {
            session.plan.steps[7].status = "completed";
        }
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

