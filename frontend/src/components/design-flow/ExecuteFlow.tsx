import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { FileText, Code2, ChevronDown } from 'lucide-react';
import { API_BASE_URL } from '../../api/client';

interface RecordingSession {
  flowName: string;
  flowSlug: string;
  timestamp: string;
  stepCount: number;
}

interface ExecuteFlowProps {
  onComplete: () => void;
  onSelectManual: (flowSlug: string) => void;
  onSelectAutomation: (flowSlug: string) => void;
}

// Helper to safely format timestamp
const formatTimestamp = (timestamp: string | null | undefined): string => {
  if (!timestamp) return 'Recent';
  
  const date = new Date(timestamp);
  // Check if date is invalid or epoch (1970)
  if (isNaN(date.getTime()) || date.getFullYear() === 1970) {
    return 'Recent';
  }
  
  return date.toLocaleDateString();
};

export const ExecuteFlow: React.FC<ExecuteFlowProps> = ({
  onComplete,
  onSelectManual,
  onSelectAutomation,
}) => {
  const [currentStep, setCurrentStep] = useState<'choice' | 'manual-select' | 'automation-select'>('choice');
  const [recordings, setRecordings] = useState<RecordingSession[]>([]);
  const [selectedRecording, setSelectedRecording] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>('');

  // Fetch available flows from vector database
  useEffect(() => {
    const fetchRecordings = async () => {
      try {
        setLoading(true);
        setError('');
        // Fetch from vector database /vector/flows endpoint
        const url = `${API_BASE_URL.replace('/api', '')}/vector/flows`;
        console.log('[ExecuteFlow] Fetching flows from vector DB:', url);
        const response = await fetch(url);
        if (response.ok) {
          const data = await response.json();
          console.log('[ExecuteFlow] Fetched flows:', data);
          setRecordings(data.flows || []);
        } else {
          const errorText = await response.text();
          console.error('[ExecuteFlow] Failed to fetch flows:', response.status, errorText);
          setError(`Failed to load flows (${response.status})`);
        }
      } catch (error) {
        console.error('[ExecuteFlow] Failed to fetch flows:', error);
        setError('Cannot connect to backend. Please ensure the server is running.');
      } finally {
        setLoading(false);
      }
    };

    if (currentStep !== 'choice') {
      fetchRecordings();
    }
  }, [currentStep]);

  const handleChoiceSelect = (choice: 'manual' | 'automation') => {
    if (choice === 'manual') {
      setCurrentStep('manual-select');
    } else {
      setCurrentStep('automation-select');
    }
  };

  const handleManualConfirm = () => {
    if (selectedRecording) {
      onSelectManual(selectedRecording);
    }
  };

  const handleAutomationConfirm = () => {
    if (selectedRecording) {
      onSelectAutomation(selectedRecording);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, x: 100 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -100 }}
      className="min-h-screen flex items-center justify-center px-8 py-12"
    >
      <div className="max-w-5xl w-full">
        <AnimatePresence mode="wait">
          {/* Choice Screen */}
          {currentStep === 'choice' && (
            <motion.div
              key="choice"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
            >
              <h1 className="text-6xl font-bold mb-8 text-center text-white">
                Choose Test Type
              </h1>
              <p className="text-xl text-gray-400 text-center mb-12">
                Select from existing recorder flows
              </p>

              <div className="grid md:grid-cols-2 gap-8">
                {/* Manual Test Cases Card */}
                <motion.button
                  whileHover={{ scale: 1.05, y: -5 }}
                  whileTap={{ scale: 0.95 }}
                  onClick={() => handleChoiceSelect('manual')}
                  className="relative group"
                >
                  <div className="h-full bg-gradient-to-br from-blue-900/40 to-blue-600/20 backdrop-blur-xl border-2 border-blue-500/30 rounded-3xl p-12 text-center hover:border-blue-400/60 transition-all shadow-2xl hover:shadow-blue-500/30">
                    <FileText size={80} className="mx-auto text-blue-400 mb-6" />
                    <h3 className="text-3xl font-bold text-white mb-4">
                      Generate Manual Test Case
                    </h3>
                    <p className="text-lg text-blue-200">
                      Select a recorded flow to generate manual test cases
                    </p>
                  </div>
                </motion.button>

                {/* Automation Script Card */}
                <motion.button
                  whileHover={{ scale: 1.05, y: -5 }}
                  whileTap={{ scale: 0.95 }}
                  onClick={() => handleChoiceSelect('automation')}
                  className="relative group"
                >
                  <div className="h-full bg-gradient-to-br from-purple-900/40 to-purple-600/20 backdrop-blur-xl border-2 border-purple-500/30 rounded-3xl p-12 text-center hover:border-purple-400/60 transition-all shadow-2xl hover:shadow-purple-500/30">
                    <Code2 size={80} className="mx-auto text-purple-400 mb-6" />
                    <h3 className="text-3xl font-bold text-white mb-4">
                      Generate Automation Test Script
                    </h3>
                    <p className="text-lg text-purple-200">
                      Select a recorded flow to generate automation scripts
                    </p>
                  </div>
                </motion.button>
              </div>
            </motion.div>
          )}

          {/* Manual Test Selection Screen */}
          {currentStep === 'manual-select' && (
            <motion.div
              key="manual-select"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
            >
              <h1 className="text-5xl font-bold mb-8 text-center text-white">
                Select Recording for Manual Test Cases
              </h1>

              <div className="bg-gradient-to-br from-blue-900/40 to-blue-600/20 backdrop-blur-xl border-2 border-blue-500/30 rounded-3xl p-12">
                <div className="mb-8">
                  <label className="block text-blue-200 mb-4 text-xl font-semibold">
                    Choose Recorded Flow
                  </label>
                  <div className="relative">
                    <select
                      value={selectedRecording}
                      onChange={(e) => setSelectedRecording(e.target.value)}
                      disabled={loading}
                      className="w-full px-6 py-4 bg-white/10 backdrop-blur-md border-2 border-white/20 rounded-xl text-white text-lg appearance-none focus:outline-none focus:border-blue-400 transition-all disabled:opacity-50"
                    >
                      <option value="" className="bg-gray-900">
                        {loading ? 'Loading recordings...' : 'Select a recording...'}
                      </option>
                      {recordings.map((rec) => (
                        <option key={rec.flowSlug} value={rec.flowSlug} className="bg-gray-900">
                          {rec.flowName} - {formatTimestamp(rec.timestamp)}
                        </option>
                      ))}
                    </select>
                    <ChevronDown className="absolute right-4 top-1/2 -translate-y-1/2 text-white/60 pointer-events-none" size={24} />
                  </div>
                  {error && (
                    <p className="mt-3 text-red-400 text-sm font-semibold">
                      ⚠️ {error}
                    </p>
                  )}
                  {recordings.length === 0 && !loading && !error && (
                    <p className="mt-3 text-blue-300/70 text-sm italic">
                      No flows found in vector database. Please record and ingest a flow first from the Design workflow.
                    </p>
                  )}
                </div>

                <div className="flex gap-4">
                  <motion.button
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                    onClick={() => setCurrentStep('choice')}
                    className="flex-1 py-4 bg-white/10 border-2 border-white/20 rounded-xl text-white font-semibold hover:bg-white/20 transition-all"
                  >
                    ← Back
                  </motion.button>
                  <motion.button
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                    onClick={handleManualConfirm}
                    disabled={!selectedRecording}
                    className="flex-1 py-4 bg-gradient-to-r from-blue-600 to-cyan-600 rounded-xl text-white font-semibold shadow-lg disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                  >
                    Continue →
                  </motion.button>
                </div>
              </div>
            </motion.div>
          )}

          {/* Automation Script Selection Screen */}
          {currentStep === 'automation-select' && (
            <motion.div
              key="automation-select"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
            >
              <h1 className="text-5xl font-bold mb-8 text-center text-white">
                Select Recording for Automation Script
              </h1>

              <div className="bg-gradient-to-br from-purple-900/40 to-purple-600/20 backdrop-blur-xl border-2 border-purple-500/30 rounded-3xl p-12">
                <div className="mb-8">
                  <label className="block text-purple-200 mb-4 text-xl font-semibold">
                    Choose Recorded Flow
                  </label>
                  <div className="relative">
                    <select
                      value={selectedRecording}
                      onChange={(e) => setSelectedRecording(e.target.value)}
                      disabled={loading}
                      className="w-full px-6 py-4 bg-white/10 backdrop-blur-md border-2 border-white/20 rounded-xl text-white text-lg appearance-none focus:outline-none focus:border-purple-400 transition-all disabled:opacity-50"
                    >
                      <option value="" className="bg-gray-900">
                        {loading ? 'Loading flows...' : 'Select a flow...'}
                      </option>
                      {recordings.map((rec) => (
                        <option key={rec.flowSlug} value={rec.flowSlug} className="bg-gray-900">
                          {rec.flowName} ({rec.stepCount} steps) - {formatTimestamp(rec.timestamp)}
                        </option>
                      ))}
                    </select>
                    <ChevronDown className="absolute right-4 top-1/2 -translate-y-1/2 text-white/60 pointer-events-none" size={24} />
                  </div>
                  {error && (
                    <p className="mt-3 text-red-400 text-sm font-semibold">
                      ⚠️ {error}
                    </p>
                  )}
                  {recordings.length === 0 && !loading && !error && (
                    <p className="mt-3 text-purple-300/70 text-sm italic">
                      No flows found in vector database. Please record and ingest a flow first from the Design workflow.
                    </p>
                  )}
                </div>

                <div className="flex gap-4">
                  <motion.button
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                    onClick={() => setCurrentStep('choice')}
                    className="flex-1 py-4 bg-white/10 border-2 border-white/20 rounded-xl text-white font-semibold hover:bg-white/20 transition-all"
                  >
                    ← Back
                  </motion.button>
                  <motion.button
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                    onClick={handleAutomationConfirm}
                    disabled={!selectedRecording}
                    className="flex-1 py-4 bg-gradient-to-r from-purple-600 to-pink-600 rounded-xl text-white font-semibold shadow-lg disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                  >
                    Continue →
                  </motion.button>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  );
};
