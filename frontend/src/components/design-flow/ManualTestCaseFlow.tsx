import React, { useState } from 'react';
import { motion } from 'framer-motion';

interface ManualTestCaseFlowProps {
  sessionName?: string;
  onComplete: () => void;
}

export const ManualTestCaseFlow: React.FC<ManualTestCaseFlowProps> = ({
  sessionName,
  onComplete,
}) => {
  const [isGenerating, setIsGenerating] = useState(false);
  const [generated, setGenerated] = useState(false);
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);

  const handleGenerate = async () => {
    setIsGenerating(true);

    try {
      // Call existing manual test case generation API
      const response = await fetch('http://localhost:8000/api/manual-test-cases/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_name: sessionName,
          output_format: 'excel',
        }),
      });

      if (response.ok) {
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        setDownloadUrl(url);
        setGenerated(true);
      }
    } catch (error) {
      console.error('Generation failed:', error);
    } finally {
      setIsGenerating(false);
    }
  };

  const handleDownload = () => {
    if (downloadUrl) {
      const link = document.createElement('a');
      link.href = downloadUrl;
      link.download = `manual_test_cases_${sessionName || 'output'}.xlsx`;
      link.click();
    }
  };

  const handleComplete = () => {
    onComplete();
  };

  return (
    <motion.div
      initial={{ opacity: 0, x: 100 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -100 }}
      className="min-h-screen flex items-center justify-center px-8"
    >
      <div className="max-w-4xl w-full">
        <motion.h1
          initial={{ y: -30, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          className="text-5xl font-bold text-white text-center mb-12"
        >
          Generate Manual Test Cases
        </motion.h1>

        <motion.div
          initial={{ scale: 0.9, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ delay: 0.2 }}
          className="bg-gray-800/50 backdrop-blur-xl rounded-3xl p-12 border border-blue-500/30"
        >
          {!generated ? (
            <div className="text-center">
              <p className="text-xl text-gray-300 mb-8">
                Session: <span className="text-blue-400 font-semibold">{sessionName}</span>
              </p>

              <motion.button
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onClick={handleGenerate}
                disabled={isGenerating}
                className={`
                  px-12 py-6 rounded-xl text-xl font-semibold
                  bg-gradient-to-r from-blue-600 to-cyan-600
                  hover:from-blue-700 hover:to-cyan-700
                  text-white shadow-lg shadow-blue-500/50
                  transition-all duration-300
                  ${isGenerating ? 'opacity-50 cursor-not-allowed' : ''}
                `}
              >
                {isGenerating ? (
                  <span className="flex items-center gap-3">
                    <motion.div
                      className="w-6 h-6 border-4 border-white border-t-transparent rounded-full"
                      animate={{ rotate: 360 }}
                      transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
                    />
                    Generating Test Cases...
                  </span>
                ) : (
                  'Generate Test Cases'
                )}
              </motion.button>

              {isGenerating && (
                <motion.div
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="mt-8 text-gray-400"
                >
                  <p>Processing recording data...</p>
                  <p className="text-sm mt-2">Creating structured test cases from your recorded flow</p>
                </motion.div>
              )}
            </div>
          ) : (
            <motion.div
              initial={{ opacity: 0, scale: 0.9 }}
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
                  className="w-24 h-24 mx-auto text-green-400"
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

              <h2 className="text-3xl font-bold text-white mb-4">
                Test Cases Generated!
              </h2>
              <p className="text-gray-300 mb-8">
                Your manual test cases are ready to download
              </p>

              <div className="flex gap-4 justify-center">
                <motion.button
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  onClick={handleDownload}
                  className="px-8 py-4 bg-green-600 hover:bg-green-700 text-white rounded-lg font-semibold"
                >
                  Download Excel
                </motion.button>

                <motion.button
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  onClick={handleComplete}
                  className="px-8 py-4 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-semibold"
                >
                  Continue
                </motion.button>
              </div>
            </motion.div>
          )}
        </motion.div>

        {/* Decorative elements */}
        {[...Array(4)].map((_, i) => (
          <motion.div
            key={i}
            className="absolute w-2 h-2 bg-blue-400 rounded-full"
            style={{
              left: `${15 + i * 25}%`,
              top: `${20 + (i % 2) * 60}%`,
            }}
            animate={{
              y: [0, -20, 0],
              opacity: [0.3, 1, 0.3],
            }}
            transition={{
              duration: 2 + i * 0.5,
              repeat: Infinity,
              delay: i * 0.3,
            }}
          />
        ))}
      </div>
    </motion.div>
  );
};
