import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

interface ChoiceSectionProps {
  onChoice: (choice: 'manual' | 'automation') => void;
  title: string;
  option1: string;
  option2: string;
}

export const ChoiceSection: React.FC<ChoiceSectionProps> = ({
  onChoice,
  title,
  option1,
  option2,
}) => {
  const [selectedChoice, setSelectedChoice] = useState<'manual' | 'automation' | null>(null);

  const handleChoice = (choice: 'manual' | 'automation') => {
    setSelectedChoice(choice);
    setTimeout(() => {
      onChoice(choice);
    }, 1000);
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="min-h-screen flex items-center justify-center px-8"
    >
      <div className="w-full max-w-6xl">
        <motion.h1
          initial={{ y: -50, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          className="text-5xl font-bold text-white text-center mb-16"
        >
          {title}
        </motion.h1>

        <div className="flex gap-12 justify-center">
          <AnimatePresence>
            {/* Option 1 - Manual Test Cases */}
            {selectedChoice !== 'automation' && (
              <motion.div
                initial={{ x: -100, opacity: 0 }}
                animate={{
                  x: 0,
                  opacity: 1,
                  scale: selectedChoice === 'manual' ? 1.1 : 1,
                }}
                exit={{
                  x: -200,
                  opacity: 0,
                  scale: 0.8,
                  transition: { duration: 0.5 },
                }}
                whileHover={{ scale: selectedChoice ? 1 : 1.05, y: -10 }}
                onClick={() => !selectedChoice && handleChoice('manual')}
                className={`
                  w-96 h-96 cursor-pointer
                  bg-gradient-to-br from-blue-900/50 to-blue-700/50
                  backdrop-blur-xl rounded-3xl p-8
                  border-2 border-blue-500/50
                  flex flex-col items-center justify-center
                  relative overflow-hidden
                  ${selectedChoice === 'manual' ? 'ring-4 ring-blue-400' : ''}
                `}
              >
                {/* Glow effect */}
                <motion.div
                  className="absolute inset-0 bg-gradient-to-r from-blue-400/20 to-cyan-400/20"
                  animate={{
                    opacity: selectedChoice === 'manual' ? [0.2, 0.5, 0.2] : 0,
                  }}
                  transition={{
                    duration: 2,
                    repeat: Infinity,
                  }}
                />

                <motion.div
                  className="relative z-10 text-center"
                  animate={{
                    scale: selectedChoice === 'manual' ? [1, 1.1, 1] : 1,
                  }}
                  transition={{
                    duration: 1,
                    repeat: selectedChoice === 'manual' ? Infinity : 0,
                  }}
                >
                  <svg
                    className="w-32 h-32 mb-6 mx-auto text-blue-300"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={1.5}
                      d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                    />
                  </svg>
                  <h2 className="text-3xl font-bold text-white mb-4">{option1}</h2>
                  <p className="text-gray-300">
                    Create detailed test case documentation
                  </p>
                </motion.div>

                {/* Floating elements */}
                <motion.div
                  className="absolute top-4 right-4 w-3 h-3 bg-blue-400 rounded-full"
                  animate={{
                    y: [0, -15, 0],
                    opacity: [0.5, 1, 0.5],
                  }}
                  transition={{
                    duration: 2,
                    repeat: Infinity,
                  }}
                />
              </motion.div>
            )}

            {/* Option 2 - Automation Scripts */}
            {selectedChoice !== 'manual' && (
              <motion.div
                initial={{ x: 100, opacity: 0 }}
                animate={{
                  x: 0,
                  opacity: 1,
                  scale: selectedChoice === 'automation' ? 1.1 : 1,
                }}
                exit={{
                  x: 200,
                  opacity: 0,
                  scale: 0.8,
                  transition: { duration: 0.5 },
                }}
                whileHover={{ scale: selectedChoice ? 1 : 1.05, y: -10 }}
                onClick={() => !selectedChoice && handleChoice('automation')}
                className={`
                  w-96 h-96 cursor-pointer
                  bg-gradient-to-br from-purple-900/50 to-purple-700/50
                  backdrop-blur-xl rounded-3xl p-8
                  border-2 border-purple-500/50
                  flex flex-col items-center justify-center
                  relative overflow-hidden
                  ${selectedChoice === 'automation' ? 'ring-4 ring-purple-400' : ''}
                `}
              >
                {/* Glow effect */}
                <motion.div
                  className="absolute inset-0 bg-gradient-to-r from-purple-400/20 to-pink-400/20"
                  animate={{
                    opacity: selectedChoice === 'automation' ? [0.2, 0.5, 0.2] : 0,
                  }}
                  transition={{
                    duration: 2,
                    repeat: Infinity,
                  }}
                />

                <motion.div
                  className="relative z-10 text-center"
                  animate={{
                    scale: selectedChoice === 'automation' ? [1, 1.1, 1] : 1,
                  }}
                  transition={{
                    duration: 1,
                    repeat: selectedChoice === 'automation' ? Infinity : 0,
                  }}
                >
                  <svg
                    className="w-32 h-32 mb-6 mx-auto text-purple-300"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={1.5}
                      d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"
                    />
                  </svg>
                  <h2 className="text-3xl font-bold text-white mb-4">{option2}</h2>
                  <p className="text-gray-300">
                    Build automated test scripts
                  </p>
                </motion.div>

                {/* Floating elements */}
                <motion.div
                  className="absolute top-4 right-4 w-3 h-3 bg-purple-400 rounded-full"
                  animate={{
                    y: [0, -15, 0],
                    opacity: [0.5, 1, 0.5],
                  }}
                  transition={{
                    duration: 2,
                    repeat: Infinity,
                    delay: 0.5,
                  }}
                />
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </motion.div>
  );
};
