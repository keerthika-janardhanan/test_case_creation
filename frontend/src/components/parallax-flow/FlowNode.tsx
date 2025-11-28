import React from 'react';
import { motion } from 'framer-motion';
import { FlowNodeData } from './types';
import { CheckCircle2, Circle, Loader2 } from 'lucide-react';

interface FlowNodeProps {
  node: FlowNodeData;
  onClick?: () => void;
  isMainCharacter?: boolean;
}

export const NODE_WIDTH = 280;
export const NODE_HEIGHT = 280;

const colorSchemes = {
  blue: {
    bg: 'from-blue-600/40 to-blue-800/30',
    border: 'border-blue-400/50',
    text: 'text-blue-100',
    glow: 'shadow-blue-500/40',
    active: 'border-blue-300',
    progressFrom: 'from-blue-400',
    progressTo: 'to-cyan-500',
  },
  purple: {
    bg: 'from-purple-600/40 to-purple-800/30',
    border: 'border-purple-400/50',
    text: 'text-purple-100',
    glow: 'shadow-purple-500/40',
    active: 'border-purple-300',
    progressFrom: 'from-purple-400',
    progressTo: 'to-pink-500',
  },
  green: {
    bg: 'from-green-600/40 to-green-800/30',
    border: 'border-green-400/50',
    text: 'text-green-100',
    glow: 'shadow-green-500/40',
    active: 'border-green-300',
    progressFrom: 'from-green-400',
    progressTo: 'to-emerald-500',
  },
  amber: {
    bg: 'from-amber-600/40 to-amber-800/30',
    border: 'border-amber-400/50',
    text: 'text-amber-100',
    glow: 'shadow-amber-500/40',
    active: 'border-amber-300',
    progressFrom: 'from-amber-400',
    progressTo: 'to-orange-500',
  },
  cyan: {
    bg: 'from-cyan-600/40 to-cyan-800/30',
    border: 'border-cyan-400/50',
    text: 'text-cyan-100',
    glow: 'shadow-cyan-500/40',
    active: 'border-cyan-300',
    progressFrom: 'from-cyan-400',
    progressTo: 'to-blue-500',
  },
  rose: {
    bg: 'from-rose-600/40 to-rose-800/30',
    border: 'border-rose-400/50',
    text: 'text-rose-100',
    glow: 'shadow-rose-500/40',
    active: 'border-rose-300',
    progressFrom: 'from-rose-400',
    progressTo: 'to-pink-500',
  },
};

export const FlowNode: React.FC<FlowNodeProps> = ({ node, onClick, isMainCharacter = false }) => {
  const { status, label, description, progress, icon, color = 'blue' } = node;
  const colorScheme = colorSchemes[color as keyof typeof colorSchemes] || colorSchemes.blue;

  const isClickable = status === 'revealed' || status === 'active';
  const isCompleted = status === 'completed';
  const isProcessing = status === 'processing';

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.5, y: 20 }}
      animate={{
        opacity: status === 'hidden' ? 0 : 1,
        scale: status === 'hidden' ? 0.5 : isMainCharacter ? 1.1 : 1,
        y: 0,
      }}
      transition={{ 
        duration: 0.6, 
        type: 'spring', 
        stiffness: 100,
        delay: status === 'hidden' ? 0 : 0.1 
      }}
      style={{
        width: NODE_WIDTH,
        height: NODE_HEIGHT,
        position: 'absolute',
        left: node.position.x,
        top: node.position.y,
        zIndex: isMainCharacter ? 100 : 10,
      }}
      className="flex items-center justify-center"
    >
      <motion.div
        whileHover={isClickable ? { scale: 1.05, y: -5 } : {}}
        whileTap={isClickable ? { scale: 0.95 } : {}}
        onClick={isClickable ? onClick : undefined}
        className={`
          relative w-full h-full rounded-3xl backdrop-blur-xl border-2
          bg-gradient-to-br ${colorScheme.bg}
          ${isClickable ? 'cursor-pointer' : 'cursor-default'}
          ${isMainCharacter ? 'border-4 ' + colorScheme.active + ' ring-4 ring-white/20' : colorScheme.border}
          ${isCompleted ? 'opacity-80' : 'opacity-100'}
          shadow-2xl ${colorScheme.glow}
          transition-all duration-300
          flex flex-col items-center justify-center p-6
        `}
      >
        {/* Circular Progress Indicator (Top Right) */}
        {isProcessing && progress !== undefined && (
          <div className="absolute top-4 right-4">
            <svg className="w-12 h-12 transform -rotate-90">
              <circle
                cx="24"
                cy="24"
                r="20"
                stroke="currentColor"
                strokeWidth="3"
                fill="none"
                className="text-white/20"
              />
              <motion.circle
                cx="24"
                cy="24"
                r="20"
                stroke="currentColor"
                strokeWidth="3"
                fill="none"
                className="text-white"
                initial={{ strokeDasharray: '0 999' }}
                animate={{ strokeDasharray: `${(progress / 100) * 125.6} 999` }}
                transition={{ duration: 0.3 }}
              />
            </svg>
            <div className="absolute inset-0 flex items-center justify-center">
              <span className="text-xs font-bold text-white">{Math.round(progress)}%</span>
            </div>
          </div>
        )}

        {/* Spinning Loader (when progress not available) */}
        {isProcessing && progress === undefined && (
          <motion.div
            className="absolute top-4 right-4"
            animate={{ rotate: 360 }}
            transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
          >
            <Loader2 className="w-8 h-8 text-white" />
          </motion.div>
        )}

        {/* Completion Check Mark */}
        {isCompleted && (
          <motion.div
            initial={{ scale: 0, rotate: -180 }}
            animate={{ scale: 1, rotate: 0 }}
            transition={{ type: 'spring', stiffness: 200 }}
            className="absolute top-4 right-4"
          >
            <CheckCircle2 className="w-10 h-10 text-green-400" />
          </motion.div>
        )}

        {/* Icon */}
        {icon && (
          <motion.div
            animate={isProcessing ? { scale: [1, 1.1, 1] } : {}}
            transition={isProcessing ? { duration: 2, repeat: Infinity } : {}}
            className={`mb-4 ${colorScheme.text}`}
          >
            {icon}
          </motion.div>
        )}

        {/* Label */}
        <h3 className="text-2xl font-bold text-white text-center mb-2">
          {label}
        </h3>

        {/* Description */}
        {description && (
          <p className="text-sm text-gray-300 text-center mb-3 px-2">
            {description}
          </p>
        )}

        {/* Internal Progress Bar */}
        {isProcessing && progress !== undefined && (
          <div className="w-full mt-auto px-2">
            <div className="flex justify-between items-center mb-2">
              <span className="text-xs text-gray-300">Processing...</span>
              <span className="text-xs font-semibold text-white">{Math.round(progress)}%</span>
            </div>
            <div className="w-full h-2.5 bg-white/10 rounded-full overflow-hidden">
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${progress}%` }}
                transition={{ duration: 0.3 }}
                className={`h-full bg-gradient-to-r ${colorScheme.progressFrom} ${colorScheme.progressTo} rounded-full relative overflow-hidden`}
              >
                {/* Shimmer effect */}
                <motion.div
                  className="absolute inset-0 bg-gradient-to-r from-transparent via-white/30 to-transparent"
                  animate={{ x: ['-100%', '100%'] }}
                  transition={{ duration: 1.5, repeat: Infinity, ease: 'linear' }}
                />
              </motion.div>
            </div>
          </div>
        )}

        {/* Click Indicator Pulse */}
        {isClickable && !isProcessing && (
          <motion.div
            animate={{ scale: [1, 1.3, 1], opacity: [0.5, 1, 0.5] }}
            transition={{ duration: 2, repeat: Infinity }}
            className="absolute bottom-4"
          >
            <Circle className="w-4 h-4 text-white/60 fill-white/20" />
          </motion.div>
        )}

        {/* Main Character Glow Effect */}
        {isMainCharacter && (
          <motion.div
            className="absolute inset-0 rounded-3xl"
            animate={{
              boxShadow: [
                '0 0 20px rgba(255, 255, 255, 0.2)',
                '0 0 40px rgba(255, 255, 255, 0.4)',
                '0 0 20px rgba(255, 255, 255, 0.2)',
              ],
            }}
            transition={{ duration: 2, repeat: Infinity }}
          />
        )}
      </motion.div>
    </motion.div>
  );
};

export const NODE_DIMENSIONS = { width: NODE_WIDTH, height: NODE_HEIGHT };
