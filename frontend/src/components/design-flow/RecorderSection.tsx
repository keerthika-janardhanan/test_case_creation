import React, { useState } from 'react';
import { motion } from 'framer-motion';

interface RecorderSectionProps {
  onComplete: (sessionName: string) => void;
}

export const RecorderSection: React.FC<RecorderSectionProps> = ({ onComplete }) => {
  const [isRecording, setIsRecording] = useState(false);
  const [isIngesting, setIsIngesting] = useState(false);
  const [sessionName, setSessionName] = useState('');
  const [showSessionInput, setShowSessionInput] = useState(false);

  const handleStartRecording = async () => {
    if (!sessionName.trim()) {
      setShowSessionInput(true);
      return;
    }

    setIsRecording(true);
    setShowSessionInput(false);

    try {
      // Call the existing recorder API
      const response = await fetch('http://localhost:8000/api/recorder/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_name: sessionName,
          url: 'https://example.com', // This will be customizable
        }),
      });

      if (response.ok) {
        // Recording started - wait for user to finish
        // In a real scenario, you'd poll for completion
        setTimeout(() => {
          setIsRecording(false);
          handleIngest();
        }, 3000); // Simulated for now
      }
    } catch (error) {
      console.error('Recording failed:', error);
      setIsRecording(false);
    }
  };

  const handleIngest = async () => {
    setIsIngesting(true);

    try {
      // Call the existing ingest API
      const response = await fetch('http://localhost:8000/api/ingest/recordings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_name: sessionName,
        }),
      });

      if (response.ok) {
        setTimeout(() => {
          setIsIngesting(false);
          onComplete(sessionName);
        }, 2000);
      }
    } catch (error) {
      console.error('Ingestion failed:', error);
      setIsIngesting(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="min-h-screen flex items-center justify-center px-8"
    >
      <div className="text-center max-w-2xl">
        <motion.h1
          initial={{ y: -50, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          className="text-5xl font-bold text-white mb-8"
        >
          Start Recording
        </motion.h1>

        {showSessionInput || !sessionName ? (
          <motion.div
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            className="mb-8"
          >
            <input
              type="text"
              value={sessionName}
              onChange={(e) => setSessionName(e.target.value)}
              placeholder="Enter session name..."
              className="w-full px-6 py-4 bg-gray-800/50 border border-gray-700 rounded-lg text-white text-xl focus:outline-none focus:border-blue-500 transition-colors"
              autoFocus
            />
          </motion.div>
        ) : null}

        {/* Floating Recorder Button */}
        <motion.button
          whileHover={{ scale: 1.1, rotate: 5 }}
          whileTap={{ scale: 0.95 }}
          onClick={handleStartRecording}
          disabled={isRecording || isIngesting}
          className={`
            relative w-64 h-64 rounded-full
            bg-gradient-to-br from-red-500 to-pink-600
            shadow-2xl shadow-red-500/50
            flex items-center justify-center
            transition-all duration-300
            ${isRecording || isIngesting ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
          `}
        >
          {/* Pulsing ring animation */}
          {(isRecording || isIngesting) && (
            <>
              <motion.div
                className="absolute inset-0 rounded-full border-4 border-red-400"
                animate={{
                  scale: [1, 1.5, 1],
                  opacity: [1, 0, 1],
                }}
                transition={{
                  duration: 2,
                  repeat: Infinity,
                }}
              />
              <motion.div
                className="absolute inset-0 rounded-full border-4 border-pink-400"
                animate={{
                  scale: [1, 1.5, 1],
                  opacity: [1, 0, 1],
                }}
                transition={{
                  duration: 2,
                  repeat: Infinity,
                  delay: 0.5,
                }}
              />
            </>
          )}

          {/* Icon */}
          <div className="relative z-10">
            {!isRecording && !isIngesting ? (
              <svg
                className="w-24 h-24 text-white"
                fill="currentColor"
                viewBox="0 0 24 24"
              >
                <circle cx="12" cy="12" r="8" />
              </svg>
            ) : isRecording ? (
              <motion.svg
                className="w-24 h-24 text-white"
                fill="currentColor"
                viewBox="0 0 24 24"
                animate={{ rotate: 360 }}
                transition={{ duration: 2, repeat: Infinity, ease: 'linear' }}
              >
                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 14.5v-9l6 4.5-6 4.5z" />
              </motion.svg>
            ) : (
              <motion.svg
                className="w-24 h-24 text-white"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
                animate={{ scale: [1, 1.2, 1] }}
                transition={{ duration: 1, repeat: Infinity }}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
                />
              </motion.svg>
            )}
          </div>
        </motion.button>

        {/* Status text */}
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="mt-8 text-2xl text-gray-300"
        >
          {isRecording
            ? 'Recording in progress...'
            : isIngesting
            ? 'Ingesting into vector database...'
            : sessionName
            ? 'Click to start recording'
            : 'Enter a session name to begin'}
        </motion.p>

        {/* Floating particles */}
        {[...Array(6)].map((_, i) => (
          <motion.div
            key={i}
            className="absolute w-2 h-2 bg-red-400 rounded-full"
            style={{
              left: `${20 + i * 15}%`,
              top: `${30 + (i % 2) * 40}%`,
            }}
            animate={{
              y: [0, -20, 0],
              opacity: [0.3, 1, 0.3],
            }}
            transition={{
              duration: 2 + i * 0.3,
              repeat: Infinity,
              delay: i * 0.2,
            }}
          />
        ))}
      </div>
    </motion.div>
  );
};
