import React from 'react';
import { motion } from 'framer-motion';
import { ConnectionData } from './types';

interface ConnectionLineProps {
  connection: ConnectionData;
  fromPos: { x: number; y: number };
  toPos: { x: number; y: number };
  nodeWidth: number;
  nodeHeight: number;
  scrollX: number;
}

export const ConnectionLine: React.FC<ConnectionLineProps> = ({
  connection,
  fromPos,
  toPos,
  nodeWidth,
  nodeHeight,
  scrollX,
}) => {
  const { status, direction, flowType } = connection;

  // Calculate start and end points (center of nodes)
  const startX = fromPos.x + nodeWidth / 2;
  const startY = fromPos.y + nodeHeight / 2;
  const endX = toPos.x + nodeWidth / 2;
  const endY = toPos.y + nodeHeight / 2;

  // Create smooth curved path
  const deltaX = endX - startX;
  const deltaY = endY - startY;
  const controlPointOffset = Math.abs(deltaX) * 0.5;
  
  // For horizontal flow, create horizontal curves
  const controlPoint1X = startX + controlPointOffset;
  const controlPoint1Y = startY;
  const controlPoint2X = endX - controlPointOffset;
  const controlPoint2Y = endY;

  const path = `M ${startX} ${startY} C ${controlPoint1X} ${controlPoint1Y}, ${controlPoint2X} ${controlPoint2Y}, ${endX} ${endY}`;

  // Calculate path length for animation
  const pathLength = Math.sqrt(Math.pow(deltaX, 2) + Math.pow(deltaY, 2));

  // Color based on flow type and status
  let color = '#4b5563'; // gray default
  if (status === 'completed') {
    color = '#10b981'; // green
  } else if (status === 'active') {
    if (flowType === 'recorder') {
      color = '#3b82f6'; // blue
    } else if (flowType === 'execute') {
      color = '#a855f7'; // purple
    } else {
      color = '#06b6d4'; // cyan
    }
  }

  return (
    <svg
      className="absolute top-0 left-0 pointer-events-none"
      style={{
        width: '100%',
        height: '100%',
        zIndex: 0,
      }}
    >
      <defs>
        {/* Gradient for the line */}
        <linearGradient
          id={`gradient-${connection.id}`}
          gradientUnits="userSpaceOnUse"
          x1={startX}
          y1={startY}
          x2={endX}
          y2={endY}
        >
          <stop offset="0%" stopColor={color} stopOpacity="0.6" />
          <stop offset="50%" stopColor={color} stopOpacity="1" />
          <stop offset="100%" stopColor={color} stopOpacity="0.6" />
        </linearGradient>

        {/* Animated gradient for flow */}
        <linearGradient id={`flow-gradient-${connection.id}`}>
          <stop offset="0%" stopColor={color} stopOpacity="0.3">
            <animate
              attributeName="offset"
              values="-0.5;-0.3;0"
              dur="2s"
              repeatCount="indefinite"
            />
          </stop>
          <stop offset="30%" stopColor={color} stopOpacity="1">
            <animate
              attributeName="offset"
              values="0;0.3;0.7"
              dur="2s"
              repeatCount="indefinite"
            />
          </stop>
          <stop offset="100%" stopColor={color} stopOpacity="0.3">
            <animate
              attributeName="offset"
              values="0.7;1;1.5"
              dur="2s"
              repeatCount="indefinite"
            />
          </stop>
        </linearGradient>

        {/* Glow filter */}
        <filter id={`glow-${connection.id}`}>
          <feGaussianBlur stdDeviation="3" result="coloredBlur" />
          <feMerge>
            <feMergeNode in="coloredBlur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      {/* Base line */}
      <motion.path
        d={path}
        stroke={`url(#gradient-${connection.id})`}
        strokeWidth="3"
        fill="none"
        opacity={status === 'inactive' ? 0.2 : 0.6}
        initial={{ pathLength: 0, opacity: 0 }}
        animate={{ pathLength: 1, opacity: status === 'inactive' ? 0.2 : 0.6 }}
        transition={{ duration: 0.8, ease: 'easeInOut' }}
        filter={status === 'active' ? `url(#glow-${connection.id})` : undefined}
      />

      {/* Animated flowing line */}
      {status === 'active' && (
        <motion.path
          d={path}
          stroke={`url(#flow-gradient-${connection.id})`}
          strokeWidth="4"
          fill="none"
          initial={{ pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ duration: 0.8, ease: 'easeInOut' }}
          filter={`url(#glow-${connection.id})`}
        />
      )}

      {/* Flowing particles */}
      {status === 'active' && (
        <>
          {[0, 0.33, 0.66].map((delay, index) => (
            <g key={index}>
              {/* Main particle */}
              <motion.circle
                r="5"
                fill={color}
                initial={{ opacity: 0 }}
                animate={{
                  opacity: [0, 1, 1, 0],
                }}
                transition={{
                  duration: 2.5,
                  repeat: Infinity,
                  ease: 'linear',
                  delay: delay * 2.5,
                }}
                filter={`url(#glow-${connection.id})`}
              >
                <animateMotion
                  dur="2.5s"
                  repeatCount="indefinite"
                  begin={`${delay * 2.5}s`}
                  path={path}
                />
              </motion.circle>
              
              {/* Trailing glow */}
              <motion.circle
                r="8"
                fill={color}
                opacity="0.3"
                initial={{ opacity: 0 }}
                animate={{
                  opacity: [0, 0.3, 0.3, 0],
                }}
                transition={{
                  duration: 2.5,
                  repeat: Infinity,
                  ease: 'linear',
                  delay: delay * 2.5,
                }}
                filter={`url(#glow-${connection.id})`}
              >
                <animateMotion
                  dur="2.5s"
                  repeatCount="indefinite"
                  begin={`${delay * 2.5}s`}
                  path={path}
                />
              </motion.circle>
            </g>
          ))}
        </>
      )}
    </svg>
  );
};
