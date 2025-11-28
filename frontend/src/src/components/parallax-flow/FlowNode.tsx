import React from 'react';
import { motion } from 'framer-motion';
import { FlowNodeData } from './types';
import { CheckCircle2, Circle, Loader2 } from 'lucide-react';

interface FlowNodeProps {
  node: FlowNodeData;
  onClick?: () => void;
  scale?: number;
}

const NODE_WIDTH = 280;
const NODE_HEIGHT = 280;

const colorSchemes = {
  blue: {
    bg: 'from-blue-600/30 to-blue-800/20',
    border: 'border-blue-400/40',
    text: 'text-blue-100',
    glow: 'shadow-blue-500/30',
    active: 'border-blue-300',
  },
  purple: {
    bg: 'from-purple-600/30 to-purple-800/20',
    border: 'border-purple-400/40',
    text: 'text-purple-100',
    glow: 'shadow-purple-500/30',
    active: 'border-purple-300',
  },
  green: {
    bg: 'from-green-600/30 to-green-800/20',
    border: 'border-green-400/40',
    text: 'text-green-100',
    glow: 'shadow-green-500/30',
    active: 'border-green-300',
  },
  amber: {
    bg: 'from-amber-600/30 to-amber-800/20',
    border: 'border-amber-400/40',
    text: 'text-amber-100',
    glow: 'shadow-amber-500/30',
    active: 'border-amber-300',
  },
  cyan: {
    bg: 'from-cyan-600/30 to-cyan-800/20',
    border: 'border-cyan-400/40',
    text: 'text-cyan-100',
    glow: 'shadow-cyan-500/30',
    active: 'border-cyan-300',
  },
  rose: {
    bg: 'from-rose-600/30 to-rose-800/20',
    border: 'border-rose-400/40',
    text: 'text-rose-100',
    glow: 'shadow-rose-500/30',
    active: 'border-rose-300',
  },
};

export const FlowNode: React.FC<FlowNodeProps> = ({ node, onClick, scale = 1 }) => {
  const { status, label, description, progress, icon, color = 'blue' } = node;
  const colorScheme = colorSchemes[color as keyof typeof colorSchemes] || colorSchemes.blue;

  const isClickable = status === 'revealed' || status === 'active';
  const isCompleted = status === 'completed';
  const isProcessing = status === 'processing';

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.8 }}
      animate={{
        opacity: status === 'hidden' ? 0 : 1,
        scale: status === 'hidden' ? 0.8 : 1,
      }}
      transition={{ duration: 0.5, type: 'spring', stiffness: 100 }}
      style={{
        width: NODE_WIDTH * scale,
        height: NODE_HEIGHT * scale,
        position: 'absolute',
        left: node.position.x,
        top: node.position.y,
      }}
      className="flex items-center justify-center"
    >
      <motion.div
        whileHover={isClickable ? { scale: 1.05, y: -5 } : {}}
        whileTap={isClickable ? { scale: 0.98 } : {}}
        onClick={isClickable ? onClick : undefined}
        className={`
          relative w-full h-full rounded-3xl backdrop-blur-xl border-2
          bg-gradient-to-br ${colorScheme.bg}
          ${isClickable ? 'cursor-pointer' : 'cursor-default'}
          ${status === 'active' ? colorScheme.active + ' border-4' : colorScheme.border}
          ${isCompleted ? 'opacity-75' : 'opacity-100'}
          shadow-2xl ${colorScheme.glow}
          transition-all duration-300
          flex flex-col items-center justify-center p-6
        `}
      >
        {/* Circular Progress Indicator */}
        {isProcessing && (
          <motion.div
            className="absolute top-4 right-4"
            animate={{ rotate: 360 }}
            transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
          >
            <Loader2 className="w-6 h-6 text-white" />
          </motion.div>
        )}

        {/* Status Indicator */}
        {isCompleted && (
          <motion.div
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            className="absolute top-4 right-4"
          >
            <CheckCircle2 className="w-8 h-8 text-green-400" />
          </motion.div>
        )}

        {/* Icon */}
        {icon && (
          <motion.div
            animate={isProcessing ? { scale: [1, 1.1, 1] } : {}}
            transition={isProcessing ? { duration: 2, repeat: Infinity } : {}}
            className={`mb-6 ${colorScheme.text}`}
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
          <p className="text-sm text-gray-300 text-center mb-4">
            {description}
          </p>
        )}

        {/* Progress Bar (inside node) */}
        {isProcessing && progress !== undefined && (
          <div className="w-full mt-4">
            <div className="flex justify-between items-center mb-2">
              <span className="text-xs text-gray-300">Processing...</span>
              <span className="text-xs font-semibold text-white">{Math.round(progress)}%</span>
            </div>
            <div className="w-full h-2 bg-white/10 rounded-full overflow-hidden">
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${progress}%` }}
                transition={{ duration: 0.3 }}
                className="h-full bg-gradient-to-r from-blue-400 to-purple-500 rounded-full"
              />
            </div>
          </div>
        )}

        {/* Click Indicator */}
        {isClickable && !isProcessing && (
          <motion.div
            animate={{ scale: [1, 1.2, 1] }}
            transition={{ duration: 1.5, repeat: Infinity }}
            className="absolute bottom-4"
          >
            <Circle className="w-4 h-4 text-white/50" />
          </motion.div>
        )}
      </motion.div>
    </motion.div>
  );
};

export const NODE_DIMENSIONS = { width: NODE_WIDTH, height: NODE_HEIGHT };
