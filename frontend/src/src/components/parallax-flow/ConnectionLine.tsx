import React from 'react';
import { motion } from 'framer-motion';
import { ConnectionData } from './types';

interface ConnectionLineProps {
  connection: ConnectionData;
  fromPos: { x: number; y: number };
  toPos: { x: number; y: number };
  nodeWidth: number;
  nodeHeight: number;
}

export const ConnectionLine: React.FC<ConnectionLineProps> = ({
  connection,
  fromPos,
  toPos,
  nodeWidth,
  nodeHeight,
}) => {
  const { status, direction } = connection;

  // Calculate start and end points (center of nodes)
  const startX = fromPos.x + nodeWidth / 2;
  const startY = fromPos.y + nodeHeight / 2;
  const endX = toPos.x + nodeWidth / 2;
  const endY = toPos.y + nodeHeight / 2;

  // Create curved path for better visuals
  const midX = (startX + endX) / 2;
  const controlPoint1X = startX + (midX - startX) * 0.5;
  const controlPoint2X = midX + (endX - midX) * 0.5;

  const path = `M ${startX} ${startY} C ${controlPoint1X} ${startY}, ${controlPoint2X} ${endY}, ${endX} ${endY}`;

  // Calculate path length for animation
  const pathLength = Math.sqrt(Math.pow(endX - startX, 2) + Math.pow(endY - startY, 2));

  // Color based on status
  const color =
    status === 'completed'
      ? '#10b981' // green
      : status === 'active'
      ? '#3b82f6' // blue
      : '#4b5563'; // gray

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
        {/* Gradient for flow animation */}
        <linearGradient
          id={`gradient-${connection.id}`}
          gradientUnits="userSpaceOnUse"
          x1="0%"
          y1="0%"
          x2="100%"
          y2="0%"
        >
          <stop offset="0%" stopColor={color} stopOpacity="0" />
          <stop offset="50%" stopColor={color} stopOpacity="1" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>

        {/* Animated gradient for flow */}
        <linearGradient id={`animated-gradient-${connection.id}`}>
          <stop offset="0%" stopColor={color} stopOpacity="0.3">
            <animate
              attributeName="offset"
              values="-2;-1;0"
              dur="2s"
              repeatCount="indefinite"
            />
          </stop>
          <stop offset="50%" stopColor={color} stopOpacity="1">
            <animate
              attributeName="offset"
              values="-1;0;1"
              dur="2s"
              repeatCount="indefinite"
            />
          </stop>
          <stop offset="100%" stopColor={color} stopOpacity="0.3">
            <animate
              attributeName="offset"
              values="0;1;2"
              dur="2s"
              repeatCount="indefinite"
            />
          </stop>
        </linearGradient>
      </defs>

      {/* Base line */}
      <motion.path
        d={path}
        stroke={color}
        strokeWidth="2"
        fill="none"
        opacity={status === 'inactive' ? 0.2 : 0.4}
        initial={{ pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={{ duration: 0.8, ease: 'easeInOut' }}
      />

      {/* Animated flowing line */}
      {status === 'active' && (
        <motion.path
          d={path}
          stroke={`url(#animated-gradient-${connection.id})`}
          strokeWidth="3"
          fill="none"
          initial={{ pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ duration: 0.8, ease: 'easeInOut' }}
        />
      )}

      {/* Flowing particles */}
      {status === 'active' && (
        <>
          <motion.circle
            r="4"
            fill={color}
            initial={{ offsetDistance: '0%', opacity: 0 }}
            animate={{
              offsetDistance: direction === 'right' ? '100%' : '0%',
              opacity: [0, 1, 1, 0],
            }}
            transition={{
              duration: 2,
              repeat: Infinity,
              ease: 'linear',
              delay: 0,
            }}
            style={{ offsetPath: `path('${path}')` }}
          />
          <motion.circle
            r="4"
            fill={color}
            initial={{ offsetDistance: '0%', opacity: 0 }}
            animate={{
              offsetDistance: direction === 'right' ? '100%' : '0%',
              opacity: [0, 1, 1, 0],
            }}
            transition={{
              duration: 2,
              repeat: Infinity,
              ease: 'linear',
              delay: 0.5,
            }}
            style={{ offsetPath: `path('${path}')` }}
          />
          <motion.circle
            r="4"
            fill={color}
            initial={{ offsetDistance: '0%', opacity: 0 }}
            animate={{
              offsetDistance: direction === 'right' ? '100%' : '0%',
              opacity: [0, 1, 1, 0],
            }}
            transition={{
              duration: 2,
              repeat: Infinity,
              ease: 'linear',
              delay: 1,
            }}
            style={{ offsetPath: `path('${path}')` }}
          />
        </>
      )}
    </svg>
  );
};
