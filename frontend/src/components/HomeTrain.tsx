import React from 'react';
import { motion } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { HorizontalScroll } from './parallax/HorizontalScroll';

const cardBase = 'bg-white/90 backdrop-blur-xl rounded-3xl p-12 shadow-2xl border';

const SlideCard: React.FC<{
  title: string;
  description: string;
  gradientFrom: string;
  gradientTo: string;
  glow: string;
  iconPath: string;
  onClick: () => void;
}> = ({ title, description, gradientFrom, gradientTo, glow, iconPath, onClick }) => {
  return (
    <motion.div 
      className="h-full flex items-center justify-center px-8"
      initial={{ opacity: 0, y: 40 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ amount: 0.6, once: false }}
      transition={{ duration: 0.6 }}
    >
      <div className={`${cardBase} ${glow}`} style={{ width: '36rem' }}>
        <div className="flex justify-center mb-6">
          <div className="relative">
            <div className="absolute inset-0 rounded-3xl blur-2xl opacity-60" style={{ background: gradientFrom }} />
            <div className="relative w-24 h-24 rounded-3xl flex items-center justify-center shadow-xl" 
                 style={{ background: `linear-gradient(to bottom right, ${gradientFrom}, ${gradientTo})` }}>
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="white">
                <path d={iconPath} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
          </div>
        </div>
        <h3 className="text-3xl font-bold text-gray-900 text-center mb-3">{title}</h3>
        <p className="text-gray-600 text-center mb-8">{description}</p>
        <button
          onClick={onClick}
          className="w-full text-white font-semibold py-4 px-8 rounded-full shadow-lg hover:shadow-xl transition-all duration-300 flex items-center justify-center gap-2 group"
          style={{ background: `linear-gradient(to right, ${gradientFrom}, ${gradientTo})` }}
        >
          <span>Click to Start</span>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" className="group-hover:translate-x-1 transition-transform">
            <path d="M9 5l7 7-7 7" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>
    </motion.div>
  );
};

export const HomeTrain: React.FC = () => {
  const navigate = useNavigate();

  return (
    <HorizontalScroll>
      {/* Slide 1: Recordings */}
      <div className="w-screen h-screen flex items-center justify-center">
        <SlideCard 
          title="Recordings" 
          description="Start a new screen recording session" 
          gradientFrom="#a855f7" 
          gradientTo="#d946ef" 
          glow="#c084fc"
          iconPath="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"
          onClick={() => navigate('/design')}
        />
      </div>

      {/* Slide 2: Generate */}
      <div className="w-screen h-screen flex items-center justify-center">
        <SlideCard 
          title="Generate" 
          description="Create manual test cases and scripts from recordings" 
          gradientFrom="#60a5fa" 
          gradientTo="#818cf8" 
          glow="#93c5fd"
          iconPath="M12 6v12m6-6H6" 
          onClick={() => navigate('/design')}
        />
      </div>

      {/* Slide 3: Automate */}
      <div className="w-screen h-screen flex items-center justify-center">
        <SlideCard 
          title="Automate" 
          description="Run, self-heal and push Playwright tests" 
          gradientFrom="#34d399" 
          gradientTo="#10b981" 
          glow="#6ee7b7"
          iconPath="M13 10V3L4 14h7v7l9-11h-7z" 
          onClick={() => navigate('/execute')}
        />
      </div>
    </HorizontalScroll>
  );
};
