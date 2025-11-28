import React from 'react';
import { motion } from 'framer-motion';

export const GradientBackground: React.FC = () => {
  return (
    <div className="fixed inset-0 -z-10 overflow-hidden bg-gradient-to-br from-purple-50/30 via-white to-blue-50/30">
      {/* Large animated gradient blobs matching reference image */}
      
      {/* Top-left purple blob */}
      <motion.div
        className="absolute -top-1/4 -left-1/4 w-[800px] h-[800px] rounded-full opacity-40"
        style={{
          background: 'radial-gradient(circle, rgba(216, 180, 254, 0.6) 0%, rgba(216, 180, 254, 0.3) 40%, transparent 70%)',
        }}
        animate={{
          x: [0, 100, 0],
          y: [0, 50, 0],
          scale: [1, 1.1, 1],
        }}
        transition={{
          duration: 25,
          repeat: Infinity,
          ease: 'easeInOut',
        }}
      />

      {/* Top-right blue blob */}
      <motion.div
        className="absolute -top-1/4 -right-1/4 w-[700px] h-[700px] rounded-full opacity-40"
        style={{
          background: 'radial-gradient(circle, rgba(191, 219, 254, 0.6) 0%, rgba(191, 219, 254, 0.3) 40%, transparent 70%)',
        }}
        animate={{
          x: [0, -80, 0],
          y: [0, 60, 0],
          scale: [1, 1.15, 1],
        }}
        transition={{
          duration: 28,
          repeat: Infinity,
          ease: 'easeInOut',
        }}
      />

      {/* Bottom-left pink blob */}
      <motion.div
        className="absolute -bottom-1/4 -left-1/4 w-[750px] h-[750px] rounded-full opacity-40"
        style={{
          background: 'radial-gradient(circle, rgba(251, 207, 232, 0.6) 0%, rgba(251, 207, 232, 0.3) 40%, transparent 70%)',
        }}
        animate={{
          x: [0, 120, 0],
          y: [0, -70, 0],
          scale: [1, 1.2, 1],
        }}
        transition={{
          duration: 30,
          repeat: Infinity,
          ease: 'easeInOut',
        }}
      />

      {/* Bottom-right blue blob */}
      <motion.div
        className="absolute -bottom-1/4 -right-1/4 w-[650px] h-[650px] rounded-full opacity-40"
        style={{
          background: 'radial-gradient(circle, rgba(191, 219, 254, 0.6) 0%, rgba(191, 219, 254, 0.3) 40%, transparent 70%)',
        }}
        animate={{
          x: [0, -90, 0],
          y: [0, -80, 0],
          scale: [1, 1.12, 1],
        }}
        transition={{
          duration: 27,
          repeat: Infinity,
          ease: 'easeInOut',
        }}
      />

      {/* Center accent blob */}
      <motion.div
        className="absolute top-1/3 left-1/2 w-[600px] h-[600px] rounded-full opacity-30"
        style={{
          background: 'radial-gradient(circle, rgba(232, 121, 249, 0.4) 0%, rgba(232, 121, 249, 0.2) 40%, transparent 70%)',
          transform: 'translate(-50%, -50%)',
        }}
        animate={{
          x: [0, 60, 0],
          y: [0, -40, 0],
          scale: [1, 1.08, 1],
        }}
        transition={{
          duration: 26,
          repeat: Infinity,
          ease: 'easeInOut',
        }}
      />
    </div>
  );
};
