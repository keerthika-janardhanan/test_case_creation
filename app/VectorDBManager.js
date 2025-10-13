/**
 * VectorDBManager provides a thin Node.js wrapper around the existing Python-based
 * Chroma vector store (`app/vector_db.py`). It exposes promise-based helpers that
 * the agents can rely on for semantic lookups and context retrieval while keeping
 * caching and error handling consistent.
 */

const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");
const { promisify } = require("util");

const access = promisify(fs.access);
const readFile = promisify(fs.readFile);

/**
 * Default TTL in milliseconds for cached vector DB queries.
 */
const DEFAULT_CACHE_TTL = 45_000;

/**
 * Helper to normalise errors coming from spawned Python processes.
 * @param {number} code
 * @param {string} stderr
 * @param {string} command
 */
function buildSpawnError(code, stderr, command) {
    const error = new Error(
        `Vector DB command "${command}" failed with exit code ${code}. ${stderr || "No additional stderr output."}`
    );
    error.exitCode = code;
    error.stderr = stderr;
    return error;
}

/**
 * @typedef {Object} VectorQueryOptions
 * @property {number} [topK]
 * @property {Array<string>} [requiredTypes]
 * @property {Record<string, string | Array<string>>} [metadataEquals]
 */

/**
 * @typedef {Object} VectorRecord
 * @property {string} id
 * @property {string} content
 * @property {Record<string, any>} metadata
 */

class VectorDBManager {
    /**
     * @param {Object} [options]
     * @param {string} [options.pythonPath] - Path to Python executable.
     * @param {string} [options.dbPath] - Path to the Chroma persistence directory.
     * @param {string} [options.modulePath] - Override path to the python module (defaults to vector_db.py).
     * @param {string} [options.recordingsDir] - Directory containing UI recorder sessions.
     * @param {number} [options.cacheTTL] - Cache time in milliseconds.
     */
    constructor(options = {}) {
        this.pythonPath = options.pythonPath || process.env.PYTHON_PATH || "python";
        this.modulePath = options.modulePath || path.resolve(__dirname, "vector_db.py");
        this.dbPath = options.dbPath
            ? path.resolve(options.dbPath)
            : path.resolve(__dirname, "../vector_store");
        this.recordingsDir = options.recordingsDir
            ? path.resolve(options.recordingsDir)
            : path.resolve(__dirname, "../recordings");

        this.cacheTTL = typeof options.cacheTTL === "number" ? options.cacheTTL : DEFAULT_CACHE_TTL;

        this._cache = new Map();
    }

    /**
     * Execute the Python CLI for the vector DB and return parsed JSON.
     * @param {string} command
     * @param {Array<string>} args
     * @returns {Promise<any>}
     * @private
     */
    _runPython(command, args) {
        const pythonArgs = [
            this.modulePath,
            "--path",
            this.dbPath,
            command,
            ...args,
        ];

        return new Promise((resolve, reject) => {
            const proc = spawn(this.pythonPath, pythonArgs, {
                cwd: path.dirname(this.modulePath),
                env: {
                    ...process.env,
                    VECTOR_DB_PATH: this.dbPath,
                },
            });
            let stdout = "";
            let stderr = "";
            proc.stdout.on("data", (chunk) => {
                stdout += chunk.toString("utf8");
            });
            proc.stderr.on("data", (chunk) => {
                stderr += chunk.toString("utf8");
            });
            proc.on("error", reject);
            proc.on("close", (code) => {
                if (code !== 0) {
                    reject(buildSpawnError(code, stderr.trim(), command));
                    return;
                }
                try {
                    const parsed = stdout ? JSON.parse(stdout) : {};
                    resolve(parsed);
                } catch (err) {
                    const parseError = new Error(
                        `Failed to parse vector DB response for "${command}". Raw output: ${stdout}`
                    );
                    parseError.cause = err;
                    reject(parseError);
                }
            });
        });
    }

    /**
     * Generate a cache key for the provided query.
     * @param {string} query
     * @param {VectorQueryOptions} options
     * @returns {string}
     * @private
     */
    _cacheKey(query, options) {
        return JSON.stringify({
            query,
            options,
        });
    }

    /**
     * Determine whether the cached entry is still valid.
     * @param {{ timestamp: number }} entry
     * @returns {boolean}
     * @private
     */
    _isCacheValid(entry) {
        if (!entry) {
            return false;
        }
        const age = Date.now() - entry.timestamp;
        return age < this.cacheTTL;
    }

    /**
     * Apply metadata filtering on vector records.
     * @param {VectorRecord[]} records
     * @param {VectorQueryOptions} options
     * @returns {VectorRecord[]}
     * @private
     */
    _filterRecords(records, options = {}) {
        let filtered = Array.isArray(records) ? [...records] : [];

        if (options.requiredTypes && options.requiredTypes.length > 0) {
            const requiredSet = new Set(options.requiredTypes.map((t) => t.toLowerCase()));
            filtered = filtered.filter((record) => {
                const typeValue = record?.metadata?.type || record?.metadata?.artifact_type;
                if (!typeValue) return false;
                if (Array.isArray(typeValue)) {
                    return typeValue.some((val) => requiredSet.has(String(val).toLowerCase()));
                }
                return requiredSet.has(String(typeValue).toLowerCase());
            });
        }

        if (options.metadataEquals) {
            filtered = filtered.filter((record) => {
                const metadata = record.metadata || {};
                return Object.entries(options.metadataEquals).every(([key, expected]) => {
                    const value = metadata[key];
                    if (Array.isArray(expected)) {
                        return expected.some((candidate) =>
                            String(value).toLowerCase() === String(candidate).toLowerCase()
                        );
                    }
                    return String(value).toLowerCase() === String(expected).toLowerCase();
                });
            });
        }

        return filtered;
    }

    /**
     * Query the vector store for similar flows or artifacts.
     * @param {string} query
     * @param {VectorQueryOptions} [options]
     * @returns {Promise<VectorRecord[]>}
     */
    async querySimilarFlows(query, options = {}) {
        if (!query || !query.trim()) {
            return [];
        }
        const cacheKey = this._cacheKey(query, options);
        const cached = this._cache.get(cacheKey);
        if (this._isCacheValid(cached)) {
            return cached.value;
        }

        const topK = options.topK || 8;
        const response = await this._runPython("query", ["--top-k", String(topK), query]);
        const records = Array.isArray(response?.results) ? response.results : [];
        const filtered = this._filterRecords(records, options);
        this._cache.set(cacheKey, { value: filtered, timestamp: Date.now() });
        return filtered;
    }

    /**
     * Persist a manual or automation artifact into the vector DB for future retrieval.
     * @param {Object} payload
     * @param {string} payload.source
     * @param {string} payload.docId
     * @param {string} payload.content
     * @param {Record<string, any>} [payload.metadata]
     * @returns {Promise<void>}
     */
    async upsertDocument(payload) {
        if (!payload?.source || !payload?.docId || !payload?.content) {
            throw new Error("VectorDBManager.upsertDocument requires source, docId, and content.");
        }
        const metadata = payload.metadata ? JSON.stringify(payload.metadata) : "{}";
        await this._runPython("add", [
            payload.source,
            payload.docId,
            payload.content,
            "--metadata",
            metadata,
        ]);
        // Invalidate cache because data changed.
        this._cache.clear();
    }

    /**
     * Retrieve stored manual test cases that match a keyword.
     * @param {string} keyword
     * @param {number} [topK]
     * @returns {Promise<VectorRecord[]>}
     */
    async retrieveManualTests(keyword, topK = 5) {
        return this.querySimilarFlows(keyword, {
            topK,
            requiredTypes: ["manual_test_case", "test_case"],
        });
    }

    /**
     * List all stored documents (useful for debugging or inspection).
     * @param {number} [limit]
     * @returns {Promise<VectorRecord[]>}
     */
    async listAll(limit = 20) {
        const response = await this._runPython("list", ["--limit", String(limit)]);
        return Array.isArray(response?.results) ? response.results : [];
    }

    /**
     * Attempt to retrieve a recording metadata JSON for the supplied session ID.
     * @param {string} sessionId
     * @returns {Promise<Record<string, any> | null>}
     */
    async getRecordingMetadata(sessionId) {
        if (!sessionId) {
            return null;
        }
        const candidate = path.resolve(this.recordingsDir, sessionId, "metadata.json");
        const fallback = path.resolve(this.recordingsDir, "..", "metadata_pretty.json");
        const attempts = [candidate, fallback];

        for (const attemptPath of attempts) {
            try {
                await access(attemptPath, fs.constants.R_OK);
            } catch (err) {
                if (err.code === "ENOENT") {
                    continue;
                }
                throw err;
            }

            try {
                const buffer = await fs.promises.readFile(attemptPath);
                let parsed;
                try {
                    parsed = JSON.parse(buffer.toString("utf8"));
                } catch (utf8Error) {
                    parsed = JSON.parse(buffer.toString("utf16le"));
                }
                if (
                    parsed &&
                    parsed.session &&
                    parsed.session.id &&
                    (!sessionId || parsed.session.id === sessionId)
                ) {
                    return parsed;
                }
                if (!sessionId) {
                    return parsed;
                }
            } catch (err) {
                // Log and continue to next attempt
                // eslint-disable-next-line no-console
                console.error(`Failed to parse recorder metadata at ${attemptPath}: ${err.message}`);
            }
        }
        return null;
    }

    /**
     * Extract action steps from a recording metadata payload.
     * @param {string} sessionId
     * @returns {Promise<Array<Record<string, any>>>}
     */
    async getRecordingSteps(sessionId) {
        const metadata = await this.getRecordingMetadata(sessionId);
        if (!metadata?.actions) {
            return [];
        }
        return metadata.actions.map((action) => ({
            id: action.actionId || action.id,
            description: action.description || action.action,
            target: action.target || action.targetText || action.selector,
            raw: action,
        }));
    }

    /**
     * Convenience helper that inspects a vector record for a linked session
     * and resolves the corresponding recording steps.
     * @param {VectorRecord} record
     * @returns {Promise<Array<Record<string, any>>>}
     */
    async resolveStepsFromRecord(record) {
        const sessionId =
            record?.metadata?.session_id ||
            record?.metadata?.sessionId ||
            record?.metadata?.session ||
            null;
        if (!sessionId) {
            return [];
        }
        return this.getRecordingSteps(sessionId);
    }
}

module.exports = {
    VectorDBManager,
};
