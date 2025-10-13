/**
 * GitHubIntegration provides a resilient wrapper around git CLI for repository inspection
 * and automated commits. The implementation avoids additional npm dependencies while
 * supporting branch management, diff inspection, and selective staging so that agents
 * can safely collaborate with human reviewers.
 */

const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");
const { promisify } = require("util");

const access = promisify(fs.access);
const mkdir = promisify(fs.mkdir);
const readFile = promisify(fs.readFile);
const writeFile = promisify(fs.writeFile);

function resolveRepoPath(repoPath) {
    return path.resolve(repoPath || process.cwd());
}

function buildGitError(command, args, code, stderr) {
    const error = new Error(
        `git ${command} failed with exit code ${code}. ${stderr || "No stderr provided."}`
    );
    error.command = command;
    error.args = args;
    error.exitCode = code;
    error.stderr = stderr;
    return error;
}

/**
 * @typedef {Object} GitCommandResult
 * @property {string} stdout
 * @property {string} stderr
 * @property {number} exitCode
 */

class GitHubIntegration {
    /**
     * @param {Object} [options]
     * @param {string} [options.repoPath]
     * @param {string} [options.remoteUrl]
     * @param {string} [options.defaultBranch]
     */
    constructor(options = {}) {
        this.repoPath = resolveRepoPath(options.repoPath);
        this.remoteUrl = options.remoteUrl || null;
        this.defaultBranch = options.defaultBranch || "main";
    }

    /**
     * Spawn git command and resolve stdout/stderr.
     * @param {Array<string>} args
     * @param {Object} [options]
     * @returns {Promise<GitCommandResult>}
     * @private
     */
    _runGit(args, options = {}) {
        return new Promise((resolve, reject) => {
            const proc = spawn("git", args, {
                cwd: this.repoPath,
                env: process.env,
                stdio: ["ignore", "pipe", "pipe"],
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
                if (code !== 0 && !options.ignoreError) {
                    reject(buildGitError(args[0] || "command", args.slice(1), code, stderr.trim()));
                    return;
                }
                resolve({ stdout: stdout.trim(), stderr: stderr.trim(), exitCode: code });
            });
        });
    }

    /**
     * Ensure repository exists locally, cloning when remote is provided.
     * @returns {Promise<void>}
     */
    async ensureRepo() {
        try {
            await access(path.join(this.repoPath, ".git"), fs.constants.F_OK);
        } catch (err) {
            if (!this.remoteUrl) {
                throw new Error(
                    `Repository not found at ${this.repoPath} and no remote URL provided for cloning.`
                );
            }
            await mkdir(this.repoPath, { recursive: true });
            await new Promise((resolve, reject) => {
                const proc = spawn("git", ["clone", this.remoteUrl, this.repoPath], {
                    cwd: path.dirname(this.repoPath),
                    env: process.env,
                    stdio: "inherit",
                });
                proc.on("error", reject);
                proc.on("close", (code) => {
                    if (code !== 0) {
                        reject(new Error(`git clone exited with code ${code}`));
                    } else {
                        resolve();
                    }
                });
            });
        }
    }

    /**
     * Determine current branch.
     * @returns {Promise<string>}
     */
    async getCurrentBranch() {
        const result = await this._runGit(["rev-parse", "--abbrev-ref", "HEAD"]);
        return result.stdout;
    }

    /**
     * Fetch latest updates from remote.
     * @returns {Promise<void>}
     */
    async fetch() {
        await this._runGit(["fetch", "--all", "--prune"]);
    }

    /**
     * Checkout target branch, creating it from base when necessary.
     * @param {string} branch
     * @param {string} [base]
     * @returns {Promise<void>}
     */
    async checkoutBranch(branch, base) {
        const existing = await this._runGit(["branch", "--list", branch], { ignoreError: true });
        if (existing.stdout) {
            await this._runGit(["checkout", branch]);
            return;
        }
        const startPoint = base || this.defaultBranch;
        await this._runGit(["checkout", "-b", branch, startPoint]);
    }

    /**
     * Stage files (relative paths).
     * @param {Array<string>} files
     * @returns {Promise<void>}
     */
    async stageFiles(files) {
        if (!Array.isArray(files) || files.length === 0) {
            return;
        }
        await this._runGit(["add", ...files]);
    }

    /**
     * Commit staged changes with message.
     * @param {string} message
     * @returns {Promise<void>}
     */
    async commit(message) {
        if (!message || !message.trim()) {
            throw new Error("Commit message cannot be empty.");
        }
        await this._runGit(["commit", "-m", message]);
    }

    /**
     * Push branch to remote.
     * @param {string} branch
     * @param {Object} [options]
     * @returns {Promise<void>}
     */
    async push(branch, options = {}) {
        const remote = options.remote || "origin";
        const args = ["push", remote, branch];
        if (options.setUpstream) {
            args.splice(2, 0, "-u");
        }
        await this._runGit(args);
    }

    /**
     * Detect framework directories (pages, locators, specs, utils).
     * @returns {Promise<Record<string, string|null>>}
     */
    async detectFrameworkStructure() {
        const directories = {
            pages: ["pages", "src/pages", "page_objects", "pageObjects"],
            locators: ["locators", "selectors", "locs"],
            specs: ["tests", "specs", "e2e", "src/tests"],
            utils: ["utils", "support", "helpers", "src/utils"],
        };

        const resolved = {};
        const search = async (candidates) => {
            for (const candidate of candidates) {
                const target = path.join(this.repoPath, candidate);
                try {
                    await access(target, fs.constants.F_OK);
                    return candidate;
                } catch (err) {
                    // Ignore missing directories.
                }
            }
            return null;
        };

        for (const [key, values] of Object.entries(directories)) {
            resolved[key] = await search(values);
        }

        return resolved;
    }

    /**
     * Read repository file relative to root.
     * @param {string} filePath
     * @returns {Promise<string>}
     */
    async readFile(filePath) {
        const absolute = path.join(this.repoPath, filePath);
        const content = await readFile(absolute, "utf-8");
        return content;
    }

    /**
     * Write repository file (creates directories as needed).
     * @param {string} filePath
     * @param {string} content
     * @returns {Promise<void>}
     */
    async writeFile(filePath, content) {
        const absolute = path.join(this.repoPath, filePath);
        await mkdir(path.dirname(absolute), { recursive: true });
        await writeFile(absolute, content, "utf-8");
    }

    /**
     * Search Git tracked files for keywords (using ripgrep when available; fallback to git grep).
     * @param {Array<string>} keywords
     * @returns {Promise<Array<{file: string, line: string}>>}
     */
    async searchKeywords(keywords) {
        if (!keywords || keywords.length === 0) {
            return [];
        }
        const pattern = keywords.join("|");

        // Try ripgrep first for performance.
        const rgResult = await new Promise((resolve) => {
            const proc = spawn("rg", ["--no-heading", "--line-number", pattern], {
                cwd: this.repoPath,
                env: process.env,
                stdio: ["ignore", "pipe", "ignore"],
            });
            let stdout = "";
            proc.stdout.on("data", (chunk) => {
                stdout += chunk.toString("utf8");
            });
            proc.on("error", () => resolve(null));
            proc.on("close", (code) => {
                if (code === 0 || code === 1) {
                    resolve(stdout.trim());
                } else {
                    resolve(null);
                }
            });
        });

        const output = rgResult ?? (await this._runGit(["grep", "-n", pattern], { ignoreError: true })).stdout;
        if (!output) {
            return [];
        }
        const findings = output.split("\n").map((line) => {
            const [fileWithPath, lineNumber, text] = line.split(":", 3);
            return {
                file: fileWithPath,
                line: `[${lineNumber}] ${text}`,
            };
        });
        return findings;
    }

    /**
     * Check working tree status (staged/unstaged changes).
     * @returns {Promise<boolean>}
     */
    async hasChanges() {
        const result = await this._runGit(["status", "--short"]);
        return Boolean(result.stdout);
    }
}

module.exports = {
    GitHubIntegration,
};
