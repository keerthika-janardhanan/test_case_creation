import React from 'react';
import { motion } from 'framer-motion';
import { useNavigate } from 'react-router-dom';

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.3,
      delayChildren: 0.2,
    },
  },
};

const cardVariants = {
  hidden: { 
    opacity: 0, 
    y: 100,
    scale: 0.8,
  },
  visible: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: {
      type: 'spring' as const,
      damping: 12,
      stiffness: 100,
    },
  },
  hover: {
    scale: 1.05,
    y: -10,
    transition: {
      type: 'spring' as const,
      damping: 10,
      stiffness: 300,
    },
  },
};

const glowVariants = {
  initial: {
    boxShadow: '0 0 20px rgba(59, 130, 246, 0.3)',
  },
  hover: {
    boxShadow: [
      '0 0 20px rgba(59, 130, 246, 0.3)',
      '0 0 60px rgba(59, 130, 246, 0.6)',
      '0 0 20px rgba(59, 130, 246, 0.3)',
    ],
    transition: {
      duration: 2,
      repeat: Infinity,
    },
  },
};

export const HomePage: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-gray-900 via-slate-900 to-black relative overflow-hidden">
      {/* Animated background gradient */}
      <motion.div
        className="absolute inset-0 bg-gradient-to-r from-blue-500/10 via-purple-500/10 to-pink-500/10"
        animate={{
          backgroundPosition: ['0% 50%', '100% 50%', '0% 50%'],
        }}
        transition={{
          duration: 10,
          repeat: Infinity,
          ease: 'linear',
        }}
        style={{
          backgroundSize: '200% 200%',
        }}
      />

      <motion.div
        variants={containerVariants}
        initial="hidden"
        animate="visible"
        className="relative z-10 px-8"
      >
        {/* Title */}
        <motion.div
          initial={{ opacity: 0, y: -50 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8 }}
          className="text-center mb-16"
        >
          <h1 className="text-6xl font-bold text-white mb-4 tracking-wider">
            Test Automation Suite
          </h1>
          <p className="text-xl text-gray-400">Choose your workflow</p>
        </motion.div>

        {/* Main Options */}
        <div className="flex gap-12 items-center justify-center">
          {/* Design Card */}
          <motion.div
            variants={cardVariants}
            whileHover="hover"
            onClick={() => navigate('/design')}
            className="cursor-pointer group"
          >
            <motion.div
              variants={glowVariants}
              initial="initial"
              whileHover="hover"
              className="w-96 h-96 bg-gradient-to-br from-gray-800/90 to-gray-900/90 backdrop-blur-xl rounded-3xl p-8 border border-blue-500/30 flex flex-col items-center justify-center relative overflow-hidden"
            >
              {/* Animated border gradient */}
              <div className="absolute inset-0 bg-gradient-to-r from-blue-500 via-purple-500 to-pink-500 opacity-0 group-hover:opacity-20 transition-opacity duration-500" />
              
              <motion.div
                className="relative z-10 text-center"
                whileHover={{ scale: 1.1 }}
                transition={{ type: 'spring', stiffness: 300 }}
              >
                <svg
                  className="w-32 h-32 mb-6 mx-auto text-blue-400"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={1.5}
                    d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
                  />
                </svg>
                <h2 className="text-4xl font-bold text-white mb-4">Design</h2>
                <p className="text-gray-300 text-lg">
                  Create test cases and automation scripts
                </p>
              </motion.div>

              {/* Floating elements */}
              <motion.div
                className="absolute top-4 right-4 w-3 h-3 bg-blue-400 rounded-full"
                animate={{
                  y: [0, -10, 0],
                  opacity: [0.5, 1, 0.5],
                }}
                transition={{
                  duration: 2,
                  repeat: Infinity,
                  delay: 0,
                }}
              />
              <motion.div
                className="absolute bottom-4 left-4 w-2 h-2 bg-purple-400 rounded-full"
                animate={{
                  y: [0, -15, 0],
                  opacity: [0.5, 1, 0.5],
                }}
                transition={{
                  duration: 2.5,
                  repeat: Infinity,
                  delay: 0.5,
                }}
              />
            </motion.div>
          </motion.div>

          {/* Execute Card */}
          <motion.div
            variants={cardVariants}
            whileHover="hover"
            onClick={() => navigate('/execute')}
            className="cursor-pointer group"
          >
            <motion.div
              variants={glowVariants}
              initial="initial"
              whileHover="hover"
              className="w-96 h-96 bg-gradient-to-br from-gray-800/90 to-gray-900/90 backdrop-blur-xl rounded-3xl p-8 border border-purple-500/30 flex flex-col items-center justify-center relative overflow-hidden"
            >
              {/* Animated border gradient */}
              <div className="absolute inset-0 bg-gradient-to-r from-purple-500 via-pink-500 to-blue-500 opacity-0 group-hover:opacity-20 transition-opacity duration-500" />
              
              <motion.div
                className="relative z-10 text-center"
                whileHover={{ scale: 1.1 }}
                transition={{ type: 'spring', stiffness: 300 }}
              >
                <svg
                  className="w-32 h-32 mb-6 mx-auto text-purple-400"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={1.5}
                    d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"
                  />
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={1.5}
                    d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
                <h2 className="text-4xl font-bold text-white mb-4">Execute</h2>
                <p className="text-gray-300 text-lg">
                  Run and manage your test suites
                </p>
              </motion.div>

              {/* Floating elements */}
              <motion.div
                className="absolute top-4 right-4 w-3 h-3 bg-purple-400 rounded-full"
                animate={{
                  y: [0, -10, 0],
                  opacity: [0.5, 1, 0.5],
                }}
                transition={{
                  duration: 2,
                  repeat: Infinity,
                  delay: 0,
                }}
              />
              <motion.div
                className="absolute bottom-4 left-4 w-2 h-2 bg-pink-400 rounded-full"
                animate={{
                  y: [0, -15, 0],
                  opacity: [0.5, 1, 0.5],
                }}
                transition={{
                  duration: 2.5,
                  repeat: Infinity,
                  delay: 0.5,
                }}
              />
            </motion.div>
          </motion.div>
        </div>
      </motion.div>
    </div>
  );
};
