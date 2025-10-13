/**
 * TestOrchestrator coordinates the UI recorder, manual test generator, and automation agent.
 * It keeps track of session state, routes context between agents, and exposes ergonomic helper
 * methods for the higher-level application to drive interactive workflows.
 */

const { ManualTestGeneratorAgent } = require("./ManualTestGeneratorAgent");
const { AutomationScriptGeneratorAgent } = require("./AutomationScriptGeneratorAgent");
const { VectorDBManager } = require("./VectorDBManager");

class TestOrchestrator {
    /**
     * @param {Object} [options]
     * @param {ManualTestGeneratorAgent} [options.manualAgent]
     * @param {AutomationScriptGeneratorAgent} [options.automationAgent]
     * @param {VectorDBManager} [options.vectorDbManager]
     */
    constructor(options = {}) {
        this.vectorDb = options.vectorDbManager || new VectorDBManager(options.vectorDbOptions);
        this.manualAgent = options.manualAgent || new ManualTestGeneratorAgent({ vectorDbManager: this.vectorDb });
        this.automationAgent =
            options.automationAgent ||
            new AutomationScriptGeneratorAgent({
                vectorDbManager: this.vectorDb,
                gitOptions: options.gitOptions,
            });
        this.sessionLinks = new Map();
    }

    /**
     * Request manual test generation for a given input.
     * @param {Object} request
     * @returns {Promise<Object>}
     */
    async requestManualTestCases(request) {
        const response = await this.manualAgent.startSession(request);
        return response;
    }

    /**
     * Update or accept the manual plan.
     * @param {string} sessionId
     * @param {Object} payload
     * @returns {Promise<Object>}
     */
    async refineManualPlan(sessionId, payload) {
        return this.manualAgent.updatePlan(sessionId, payload);
    }

    /**
     * Generate final manual test cases for the session.
     * @param {string} sessionId
     * @returns {Promise<Object>}
     */
    async finaliseManualTestCases(sessionId) {
        return this.manualAgent.generateFinalTestCases(sessionId);
    }

    /**
     * Kick off automation workflow using an existing manual session ID or direct manual cases.
     * @param {Object} request
     * @param {string} [request.manualSessionId]
     * @param {Array<Object>} [request.manualTestCases]
     * @param {string} [request.keyword]
     * @returns {Promise<Object>}
     */
    async requestAutomation(request) {
        let manualCases = request.manualTestCases;
        let recordedSequences = Array.isArray(request.recordedSequences)
            ? request.recordedSequences
            : [];
        if (!manualCases && request.manualSessionId) {
            const manualSession = this.manualAgent.sessions.get(request.manualSessionId);
            if (!manualSession) {
                throw new Error(`Manual session ${request.manualSessionId} not found.`);
            }
            if (manualSession.generated?.testCases) {
                manualCases = manualSession.generated.testCases;
                if (!recordedSequences.length && Array.isArray(manualSession.recorderSequences)) {
                    recordedSequences = manualSession.recorderSequences;
                }
            } else if (manualSession.stage === "pending-generation") {
                const finalised = await this.manualAgent.generateFinalTestCases(request.manualSessionId);
                manualCases = finalised.manualTestCases;
                if (!recordedSequences.length && Array.isArray(manualSession.recorderSequences)) {
                    recordedSequences = manualSession.recorderSequences;
                }
            } else {
                throw new Error("Manual session must be accepted and finalised before automation can begin.");
            }
        }
        if (!manualCases) {
            throw new Error("No manual test cases available for automation.");
        }
        const automationResponse = await this.automationAgent.startSession({
            manualTestCases: manualCases,
            keyword: request.keyword,
            recordedSequences,
        });
        if (request.manualSessionId) {
            this.sessionLinks.set(request.manualSessionId, automationResponse.sessionId);
        }
        return automationResponse;
    }

    /**
     * Accept or adjust automation plan.
     * @param {string} sessionId
     * @param {Object} payload
     * @returns {Promise<Object>}
     */
    async refineAutomationPlan(sessionId, payload) {
        return this.automationAgent.updatePlan(sessionId, payload);
    }

    /**
     * Produce automation blueprint from manual cases.
     * @param {string} sessionId
     * @returns {Promise<Object>}
     */
    async prepareAutomationBlueprint(sessionId) {
        return this.automationAgent.prepareBlueprint(sessionId);
    }

    /**
     * Confirm automation blueprint prior to code generation.
     * @param {string} sessionId
     * @param {Object} payload
     * @returns {Promise<Object>}
     */
    async confirmAutomationBlueprint(sessionId, payload) {
        return this.automationAgent.confirmBlueprint(sessionId, payload);
    }

    /**
     * Generate automation code payload.
     * @param {string} sessionId
     * @returns {Promise<Object>}
     */
    async generateAutomationCode(sessionId) {
        return this.automationAgent.generateCode(sessionId);
    }

    /**
     * Write generated files to repository.
     * @param {string} sessionId
     * @returns {Promise<Object>}
     */
    async persistAutomationFiles(sessionId) {
        const writeResult = await this.automationAgent.writeFiles(sessionId);
        await this._indexAutomationArtifacts(sessionId);
        return writeResult;
    }

    /**
     * Push automation code to repository after confirmation.
     * @param {string} sessionId
     * @param {Object} options
     * @returns {Promise<Object>}
     */
    async pushAutomation(sessionId, options) {
        return this.automationAgent.pushToGitHub(sessionId, options);
    }

    /**
     * Provide quick lookup from manual session to automation session IDs.
     * @param {string} manualSessionId
     * @returns {string|null}
     */
    getLinkedAutomationSession(manualSessionId) {
        return this.sessionLinks.get(manualSessionId) || null;
    }

    /**
     * Resolve recording steps from a session ID using the manual agent's recorder bridge.
     * @param {string} sessionId
     * @returns {Promise<Array<Object>>}
     */
    async getRecordingSteps(sessionId) {
        return this.manualAgent.uiRecorder.extractSteps(sessionId);
    }

    /**
     * Persist generated automation metadata back into the vector DB for future recall.
     * @param {string} sessionId
     * @returns {Promise<void>}
     * @private
     */
    async _indexAutomationArtifacts(sessionId) {
        const automationSession = this.automationAgent.sessions.get(sessionId);
        if (!automationSession?.generatedPayload) {
            return;
        }
        const files = automationSession.generatedPayload.files || [];
        const recordedSessions = Array.isArray(automationSession.recordedSequences)
            ? automationSession.recordedSequences.map((entry) => entry.sessionId)
            : [];
        const recordedStepCount = Array.isArray(automationSession.recordedSteps)
            ? automationSession.recordedSteps.length
            : 0;
        for (const file of files) {
            try {
                await this.vectorDb.upsertDocument({
                    source: "automation_script_generator",
                    docId: `${sessionId}-${file.path}`,
                    content: file.content,
                    metadata: {
                        type: "script",
                        artifact_type: "automation_script",
                        path: file.path,
                        slug: automationSession.slug,
                        keyword: automationSession.keyword,
                        created_at: new Date().toISOString(),
                        recorder_sessions: recordedSessions,
                        recorded_step_count: recordedStepCount,
                    },
                });
            } catch (err) {
                // capture but do not break user experience
                // eslint-disable-next-line no-console
                console.error("Failed to index automation artifact", file.path, err.message);
            }
        }
    }
}

module.exports = {
    TestOrchestrator,
};
