import React from 'react';
import { motion } from 'framer-motion';
// no navigation needed in this wrapper; handled inside HomeTrain
import { HomeTrain } from './HomeTrain';

export const HomePage: React.FC = () => {

  return (
    <div className="min-h-screen flex flex-col bg-transparent relative overflow-hidden" style={{ minHeight: '100vh' }}>
      {/* Header */}
      <div className="flex items-center gap-3 p-6" style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', padding: '1.5rem' }}>
        <div 
          className="w-12 h-12 bg-gradient-to-br from-purple-500 to-pink-500 rounded-xl flex items-center justify-center shadow-lg"
          style={{
            width: '3rem',
            height: '3rem',
            background: 'linear-gradient(to bottom right, rgb(168 85 247), rgb(236 72 153))',
            borderRadius: '0.75rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 10px 15px -3px rgb(0 0 0 / 0.1)',
          }}
        >
          <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24" width="24" height="24" style={{ color: 'white' }}>
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
        </div>
        <div>
          <h1 className="text-xl font-bold text-gray-900" style={{ fontSize: '1.25rem', fontWeight: '700', color: 'rgb(17 24 39)' }}>
            Test Automation Studio
          </h1>
          <p className="text-sm text-gray-600" style={{ fontSize: '0.875rem', color: 'rgb(75 85 99)' }}>
            Record • Generate • Automate ✨
          </p>
        </div>
      </div>

      {/* Main Content - Centered */}
      <div 
        className="flex-1 flex flex-col items-center justify-center px-8 pb-20"
        style={{
          flex: '1',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '0 2rem 5rem 2rem',
        }}
      >
        {/* Hero Section */}
        <motion.div
          initial={{ opacity: 0, y: -30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          className="text-center mb-12"
          style={{ textAlign: 'center', marginBottom: '3rem' }}
        >
          <h2 className="text-5xl font-bold text-gray-900 mb-4" style={{ fontSize: '3rem', fontWeight: '700', color: 'rgb(17 24 39)', marginBottom: '1rem' }}>
            Let's Get Started!
          </h2>
          <p className="text-lg text-gray-600" style={{ fontSize: '1.125rem', color: 'rgb(75 85 99)' }}>
            Click below to begin your journey
          </p>
        </motion.div>

        {/* Train-style horizontal parallax slides */}
        <div className="w-full">
          <HomeTrain />
        </div>
      </div>
    </div>
  );
};
