import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

interface AutomationScriptFlowProps {
  sessionName?: string;
  onComplete: () => void;
}

type AutomationStep =
  | 'github-input'
  | 'keyword-input'
  | 'checking-repo'
  | 'show-existing-code'
  | 'choose-path'
  | 'editable-preview'
  | 'generate-payload'
  | 'confirm-script'
  | 'testmanager-input'
  | 'persist'
  | 'trial-run'
  | 'push-to-git'
  | 'complete';

interface RepoData {
  owner: string;
  repo: string;
  keyword: string;
}

export const AutomationScriptFlow: React.FC<AutomationScriptFlowProps> = ({
  sessionName,
  onComplete,
}) => {
  const [currentStep, setCurrentStep] = useState<AutomationStep>('github-input');
  const [repoData, setRepoData] = useState<RepoData>({
    owner: '',
    repo: '',
    keyword: '',
  });
  const [existingCode, setExistingCode] = useState<string | null>(null);
  const [refinedFlow, setRefinedFlow] = useState<string | null>(null);
  const [preview, setPreview] = useState<string>('');
  const [testManagerFile, setTestManagerFile] = useState<File | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  // GitHub input step
  const handleGithubSubmit = () => {
    setCurrentStep('keyword-input');
  };

  // Keyword input step
  const handleKeywordSubmit = async () => {
    setCurrentStep('checking-repo');
    setIsLoading(true);

    try {
      // Check if code exists in repo
      const response = await fetch('http://localhost:8000/api/automation/check-existing', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          repo_owner: repoData.owner,
          repo_name: repoData.repo,
          keyword: repoData.keyword,
        }),
      });

      const data = await response.json();

      if (data.existing_code) {
        setExistingCode(data.existing_code);
      }
      if (data.refined_flow) {
        setRefinedFlow(data.refined_flow);
      }

      setCurrentStep('show-existing-code');
    } catch (error) {
      console.error('Check failed:', error);
    } finally {
      setIsLoading(false);
    }
  };

  // Choose between existing code or refined flow
  const handleChoosePath = (path: 'existing' | 'refined') => {
    if (path === 'existing') {
      setCurrentStep('testmanager-input');
    } else {
      setPreview(refinedFlow || '// Preview of refined recorder flow\n// Edit as needed');
      setCurrentStep('editable-preview');
    }
  };

  // After editing preview
  const handlePreviewConfirm = () => {
    setCurrentStep('generate-payload');
  };

  // Generate payload
  const handleGeneratePayload = async () => {
    setIsLoading(true);
    try {
      const response = await fetch('http://localhost:8000/api/automation/generate-payload', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_name: sessionName,
          preview_content: preview,
          repo_data: repoData,
        }),
      });

      if (response.ok) {
        setCurrentStep('confirm-script');
      }
    } catch (error) {
      console.error('Payload generation failed:', error);
    } finally {
      setIsLoading(false);
    }
  };

  // Confirm script
  const handleConfirmScript = () => {
    setCurrentStep('testmanager-input');
  };

  // Test Manager upload
  const handleTestManagerUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      setTestManagerFile(file);
    }
  };

  // Persist to internal framework
  const handlePersist = async () => {
    setIsLoading(true);
    setCurrentStep('persist');

    try {
      const formData = new FormData();
      if (testManagerFile) {
        formData.append('file', testManagerFile);
      }
      formData.append('session_name', sessionName || '');
      formData.append('repo_data', JSON.stringify(repoData));

      await fetch('http://localhost:8000/api/automation/persist', {
        method: 'POST',
        body: formData,
      });

      setTimeout(() => {
        setCurrentStep('trial-run');
        setIsLoading(false);
      }, 2000);
    } catch (error) {
      console.error('Persist failed:', error);
      setIsLoading(false);
    }
  };

  // Trial run
  const handleTrialRun = async () => {
    setIsLoading(true);

    try {
      // Use the correct agentic endpoint with headed=true to launch visible browser
      const response = await fetch('http://localhost:8000/api/agentic/trial-run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          testFileContent: preview || refinedFlow || existingCode || '',
          headed: true, // Launch Chromium visibly
          frameworkRoot: undefined, // Optional: could be configured
        }),
      });

      const result = await response.json();
      
      if (result.success) {
        setTimeout(() => {
          setCurrentStep('push-to-git');
          setIsLoading(false);
        }, 1000);
      } else {
        console.error('Trial run failed:', result.logs);
        alert(`Trial run failed. Check console for details.\n\n${result.logs.substring(0, 500)}`);
        setIsLoading(false);
      }
    } catch (error) {
      console.error('Trial run failed:', error);
      alert('Trial run failed. Check console for details.');
      setIsLoading(false);
    }
  };

  // Push to Git
  const handlePushToGit = async () => {
    setIsLoading(true);

    try {
      await fetch('http://localhost:8000/api/automation/push', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          repo_owner: repoData.owner,
          repo_name: repoData.repo,
          session_name: sessionName,
        }),
      });

      setTimeout(() => {
        setCurrentStep('complete');
        setIsLoading(false);
      }, 2000);
    } catch (error) {
      console.error('Push failed:', error);
      setIsLoading(false);
    }
  };

  const handleFinalComplete = () => {
    onComplete();
  };

  return (
    <motion.div
      initial={{ opacity: 0, x: 100 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -100 }}
      className="min-h-screen flex items-center justify-center px-8 py-12"
    >
      <div className="max-w-4xl w-full">
        <AnimatePresence mode="wait">
          {/* GitHub Input */}
          {currentStep === 'github-input' && (
            <motion.div
              key="github-input"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              className="text-center"
            >
              <h1 className="text-5xl font-bold text-white mb-8">
                GitHub Repository Details
              </h1>
              <div className="bg-gray-800/50 backdrop-blur-xl rounded-3xl p-12 border border-purple-500/30">
                <div className="space-y-6">
                  <input
                    type="text"
                    placeholder="Repository Owner"
                    value={repoData.owner}
                    onChange={(e) => setRepoData({ ...repoData, owner: e.target.value })}
                    className="w-full px-6 py-4 bg-gray-700/50 border border-gray-600 rounded-lg text-white text-lg focus:outline-none focus:border-purple-500"
                  />
                  <input
                    type="text"
                    placeholder="Repository Name"
                    value={repoData.repo}
                    onChange={(e) => setRepoData({ ...repoData, repo: e.target.value })}
                    className="w-full px-6 py-4 bg-gray-700/50 border border-gray-600 rounded-lg text-white text-lg focus:outline-none focus:border-purple-500"
                  />
                </div>
                <motion.button
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  onClick={handleGithubSubmit}
                  disabled={!repoData.owner || !repoData.repo}
                  className="mt-8 px-12 py-4 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white rounded-lg text-lg font-semibold"
                >
                  Continue
                </motion.button>
              </div>
            </motion.div>
          )}

          {/* Keyword Input */}
          {currentStep === 'keyword-input' && (
            <motion.div
              key="keyword-input"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              className="text-center"
            >
              <h1 className="text-5xl font-bold text-white mb-8">
                Enter Search Keyword
              </h1>
              <div className="bg-gray-800/50 backdrop-blur-xl rounded-3xl p-12 border border-purple-500/30">
                <input
                  type="text"
                  placeholder="Keyword to search in repository..."
                  value={repoData.keyword}
                  onChange={(e) => setRepoData({ ...repoData, keyword: e.target.value })}
                  className="w-full px-6 py-4 bg-gray-700/50 border border-gray-600 rounded-lg text-white text-lg focus:outline-none focus:border-purple-500"
                />
                <motion.button
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  onClick={handleKeywordSubmit}
                  disabled={!repoData.keyword}
                  className="mt-8 px-12 py-4 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white rounded-lg text-lg font-semibold"
                >
                  Search Repository
                </motion.button>
              </div>
            </motion.div>
          )}

          {/* Checking Repo */}
          {currentStep === 'checking-repo' && (
            <motion.div
              key="checking-repo"
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              className="text-center"
            >
              <motion.div
                className="w-32 h-32 mx-auto mb-8 border-8 border-purple-500 border-t-transparent rounded-full"
                animate={{ rotate: 360 }}
                transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
              />
              <h2 className="text-3xl font-bold text-white">
                Checking repository...
              </h2>
              <p className="text-gray-400 mt-4">
                Searching for existing code with keyword: {repoData.keyword}
              </p>
            </motion.div>
          )}

          {/* Show Existing Code vs Refined Flow */}
          {currentStep === 'show-existing-code' && (
            <motion.div
              key="show-existing-code"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
            >
              <h1 className="text-4xl font-bold text-white text-center mb-8">
                Choose Your Path
              </h1>
              <div className="grid grid-cols-2 gap-8">
                {/* Existing Code */}
                <motion.div
                  whileHover={{ scale: 1.02, y: -5 }}
                  onClick={() => handleChoosePath('existing')}
                  className="bg-gray-800/50 backdrop-blur-xl rounded-2xl p-8 border border-green-500/30 cursor-pointer"
                >
                  <h3 className="text-2xl font-bold text-green-400 mb-4">
                    Use Existing Script
                  </h3>
                  <div className="bg-gray-900 rounded-lg p-4 max-h-64 overflow-auto">
                    <pre className="text-sm text-gray-300">
                      {existingCode || 'No existing code found'}
                    </pre>
                  </div>
                  <button className="mt-4 w-full px-6 py-3 bg-green-600 hover:bg-green-700 text-white rounded-lg">
                    Use This
                  </button>
                </motion.div>

                {/* Refined Recorder Flow */}
                <motion.div
                  whileHover={{ scale: 1.02, y: -5 }}
                  onClick={() => handleChoosePath('refined')}
                  className="bg-gray-800/50 backdrop-blur-xl rounded-2xl p-8 border border-purple-500/30 cursor-pointer"
                >
                  <h3 className="text-2xl font-bold text-purple-400 mb-4">
                    Refined Recorder Flow
                  </h3>
                  <div className="bg-gray-900 rounded-lg p-4 max-h-64 overflow-auto">
                    <pre className="text-sm text-gray-300">
                      {refinedFlow || 'Recorder flow will be generated'}
                    </pre>
                  </div>
                  <button className="mt-4 w-full px-6 py-3 bg-purple-600 hover:bg-purple-700 text-white rounded-lg">
                    Use This
                  </button>
                </motion.div>
              </div>
            </motion.div>
          )}

          {/* Editable Preview */}
          {currentStep === 'editable-preview' && (
            <motion.div
              key="editable-preview"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
            >
              <h1 className="text-4xl font-bold text-white text-center mb-8">
                Review & Edit Preview
              </h1>
              <div className="bg-gray-800/50 backdrop-blur-xl rounded-3xl p-8 border border-purple-500/30">
                <textarea
                  value={preview}
                  onChange={(e) => setPreview(e.target.value)}
                  className="w-full h-96 px-4 py-4 bg-gray-900 border border-gray-700 rounded-lg text-white font-mono text-sm focus:outline-none focus:border-purple-500"
                  placeholder="Edit your test script preview..."
                />
                <div className="flex gap-4 mt-6">
                  <motion.button
                    whileHover={{ scale: 1.05 }}
                    whileTap={{ scale: 0.95 }}
                    onClick={handlePreviewConfirm}
                    className="flex-1 px-8 py-4 bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-semibold"
                  >
                    Looks Good - Continue
                  </motion.button>
                </div>
              </div>
            </motion.div>
          )}

          {/* Generate Payload */}
          {currentStep === 'generate-payload' && (
            <motion.div
              key="generate-payload"
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              className="text-center"
            >
              <h1 className="text-4xl font-bold text-white mb-8">
                Generate Script Payload
              </h1>
              <motion.button
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onClick={handleGeneratePayload}
                disabled={isLoading}
                className="px-12 py-6 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 disabled:opacity-50 text-white rounded-xl text-xl font-semibold"
              >
                {isLoading ? 'Generating...' : 'Generate Payload'}
              </motion.button>
            </motion.div>
          )}

          {/* Confirm Script */}
          {currentStep === 'confirm-script' && (
            <motion.div
              key="confirm-script"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              className="text-center"
            >
              <h1 className="text-4xl font-bold text-white mb-8">
                Confirm Generated Script
              </h1>
              <div className="bg-gray-800/50 backdrop-blur-xl rounded-3xl p-12 border border-green-500/30">
                <p className="text-xl text-gray-300 mb-8">
                  Script payload generated successfully!
                </p>
                <motion.button
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  onClick={handleConfirmScript}
                  className="px-12 py-4 bg-green-600 hover:bg-green-700 text-white rounded-lg text-lg font-semibold"
                >
                  Confirm & Continue
                </motion.button>
              </div>
            </motion.div>
          )}

          {/* TestManager Upload */}
          {currentStep === 'testmanager-input' && (
            <motion.div
              key="testmanager-input"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
            >
              <h1 className="text-4xl font-bold text-white text-center mb-8">
                Upload TestManager.xlsx
              </h1>
              <div className="bg-gray-800/50 backdrop-blur-xl rounded-3xl p-12 border border-blue-500/30">
                <div className="mb-8">
                  <label className="block w-full">
                    <div className="border-2 border-dashed border-blue-500 rounded-lg p-12 text-center cursor-pointer hover:border-blue-400 transition-colors">
                      <svg
                        className="w-16 h-16 mx-auto mb-4 text-blue-400"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
                        />
                      </svg>
                      <p className="text-gray-300">
                        {testManagerFile
                          ? testManagerFile.name
                          : 'Click to upload TestManager.xlsx'}
                      </p>
                    </div>
                    <input
                      type="file"
                      accept=".xlsx,.xls"
                      onChange={handleTestManagerUpload}
                      className="hidden"
                    />
                  </label>
                </div>
                <motion.button
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  onClick={handlePersist}
                  disabled={!testManagerFile}
                  className="w-full px-8 py-4 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg text-lg font-semibold"
                >
                  Persist to Framework
                </motion.button>
              </div>
            </motion.div>
          )}

          {/* Persist */}
          {currentStep === 'persist' && (
            <motion.div
              key="persist"
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              className="text-center"
            >
              <motion.div
                className="w-32 h-32 mx-auto mb-8 border-8 border-blue-500 border-t-transparent rounded-full"
                animate={{ rotate: 360 }}
                transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
              />
              <h2 className="text-3xl font-bold text-white">
                Persisting to Internal Framework...
              </h2>
            </motion.div>
          )}

          {/* Trial Run */}
          {currentStep === 'trial-run' && (
            <motion.div
              key="trial-run"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              className="text-center"
            >
              <h1 className="text-4xl font-bold text-white mb-8">
                Run Trial Test
              </h1>
              <div className="bg-gray-800/50 backdrop-blur-xl rounded-3xl p-12 border border-yellow-500/30">
                <p className="text-xl text-gray-300 mb-8">
                  Ready to execute a trial run of your automation script
                </p>
                <motion.button
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  onClick={handleTrialRun}
                  disabled={isLoading}
                  className="px-12 py-4 bg-yellow-600 hover:bg-yellow-700 disabled:opacity-50 text-white rounded-lg text-lg font-semibold"
                >
                  {isLoading ? 'Running Trial...' : 'Start Trial Run'}
                </motion.button>
              </div>
            </motion.div>
          )}

          {/* Push to Git */}
          {currentStep === 'push-to-git' && (
            <motion.div
              key="push-to-git"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              className="text-center"
            >
              <h1 className="text-4xl font-bold text-white mb-8">
                Push to GitHub
              </h1>
              <div className="bg-gray-800/50 backdrop-blur-xl rounded-3xl p-12 border border-purple-500/30">
                <p className="text-xl text-gray-300 mb-8">
                  Trial run successful! Ready to push to repository.
                </p>
                <motion.button
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  onClick={handlePushToGit}
                  disabled={isLoading}
                  className="px-12 py-4 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white rounded-lg text-lg font-semibold"
                >
                  {isLoading ? 'Pushing...' : 'Push to Git'}
                </motion.button>
              </div>
            </motion.div>
          )}

          {/* Complete */}
          {currentStep === 'complete' && (
            <motion.div
              key="complete"
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
              className="text-center"
            >
              <motion.div
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{ type: 'spring', stiffness: 200 }}
                className="mb-8"
              >
                <svg
                  className="w-32 h-32 mx-auto text-green-400"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
              </motion.div>
              <h1 className="text-5xl font-bold text-white mb-4">
                Automation Script Complete!
              </h1>
              <p className="text-xl text-gray-400 mb-8">
                Your script has been pushed to GitHub successfully
              </p>
              <motion.button
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onClick={handleFinalComplete}
                className="px-12 py-4 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-lg font-semibold"
              >
                Continue
              </motion.button>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  );
};
