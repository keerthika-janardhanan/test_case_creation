import { motion, useMotionValue, useTransform } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { useEffect, useState, useRef } from 'react';
import { Lightbulb, Play } from 'lucide-react';

export function ImmersiveHome() {
  const navigate = useNavigate();
  const [mousePosition, setMousePosition] = useState({ x: 0, y: 0 });
  
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      setMousePosition({ 
        x: (e.clientX / window.innerWidth - 0.5) * 2,
        y: (e.clientY / window.innerHeight - 0.5) * 2,
      });
    };
    window.addEventListener('mousemove', handleMouseMove);
    return () => window.removeEventListener('mousemove', handleMouseMove);
  }, []);

  return (
    <div className="relative min-h-screen bg-black overflow-hidden">
      {/* 3D Animated background with parallax particles */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div 
          className="absolute inset-0 bg-gradient-to-br from-purple-950/30 via-slate-950/50 to-blue-950/30"
          style={{
            transform: `translate(${mousePosition.x * 20}px, ${mousePosition.y * 20}px)`,
            transition: 'transform 0.3s ease-out'
          }}
        />
        {[...Array(120)].map((_, i) => {
          const depth = Math.random();
          const size = 1 + depth * 4;
          const x = Math.random() * 100;
          const y = Math.random() * 100;
          const isBlue = depth > 0.5;
          return (
            <motion.div
              key={i}
              className="absolute rounded-full"
              style={{
                left: `${x}%`,
                top: `${y}%`,
                width: `${size}px`,
                height: `${size}px`,
                background: `radial-gradient(circle, ${isBlue ? 'rgba(168, 85, 247, 0.6)' : 'rgba(59, 130, 246, 0.4)'} 0%, transparent 70%)`,
                filter: 'blur(1px)',
                transform: `translateX(${mousePosition.x * depth * 40}px) translateY(${mousePosition.y * depth * 40}px)`,
                boxShadow: isBlue 
                  ? '0 0 20px rgba(168, 85, 247, 0.3)' 
                  : '0 0 15px rgba(59, 130, 246, 0.2)',
              }}
              animate={{
                y: [0, -30 * depth, 0],
                opacity: [0.4, 0.8, 0.4],
                scale: [1, 1 + depth * 0.3, 1],
              }}
              transition={{
                duration: 5 + Math.random() * 4,
                repeat: Infinity,
                delay: Math.random() * 3,
                ease: 'easeInOut',
              }}
            />
          );
        })}
      </div>

      {/* Main Content */}
      <div className="relative z-10 flex items-center justify-center min-h-screen px-6">
        <div className="container mx-auto">
          {/* Title with 3D effect */}
          <motion.div
            initial={{ opacity: 0, y: -80, rotateX: 45 }}
            animate={{ opacity: 1, y: 0, rotateX: 0 }}
            transition={{ duration: 1.2, delay: 0.3, type: 'spring', stiffness: 60 }}
            className="text-center mb-24"
            style={{ perspective: '1200px' }}
          >
            <motion.h1 
              className="text-8xl font-bold mb-8 bg-gradient-to-r from-blue-400 via-purple-500 to-pink-500 bg-clip-text text-transparent drop-shadow-2xl"
              animate={{
                backgroundPosition: ['0%', '100%', '0%'],
              }}
              transition={{
                duration: 8,
                repeat: Infinity,
                ease: 'linear',
              }}
              style={{
                backgroundSize: '200% 200%',
              }}
            >
              Test Automation Suite
            </motion.h1>
            <motion.p 
              className="text-3xl text-gray-300 font-light tracking-wide"
              animate={{
                opacity: [0.7, 1, 0.7],
              }}
              transition={{
                duration: 3,
                repeat: Infinity,
                ease: 'easeInOut',
              }}
            >
              Choose your workflow
            </motion.p>
          </motion.div>

          {/* Two Main Cards */}
          <div className="grid md:grid-cols-2 gap-16 max-w-6xl mx-auto">
            {/* Design Card */}
            <motion.div
              initial={{ opacity: 0, x: -150, rotateY: -25, scale: 0.8 }}
              animate={{ opacity: 1, x: 0, rotateY: 0, scale: 1 }}
              transition={{ 
                duration: 1.2, 
                delay: 0.6,
                type: 'spring',
                stiffness: 50,
              }}
              whileHover={{ 
                scale: 1.1, 
                y: -20,
                rotateY: 8,
                rotateX: 5,
                transition: { duration: 0.4 }
              }}
              whileTap={{ scale: 0.95 }}
              onClick={() => navigate('/recorder')}
              className="relative group cursor-pointer"
              style={{ 
                perspective: '1500px',
                transformStyle: 'preserve-3d',
              }}
            >
              <div className="relative bg-gradient-to-br from-blue-900/50 to-blue-600/30 backdrop-blur-2xl border-2 border-blue-500/40 rounded-[2.5rem] p-16 overflow-hidden shadow-2xl shadow-blue-500/30 transition-all duration-700 group-hover:shadow-blue-400/60 group-hover:border-blue-400/60">
                {/* Animated glowing orb */}
                <motion.div
                  className="absolute top-1/2 left-1/2 w-64 h-64 bg-blue-500/20 rounded-full blur-3xl"
                  animate={{
                    scale: [1, 1.5, 1],
                    opacity: [0.3, 0.6, 0.3],
                  }}
                  transition={{
                    duration: 4,
                    repeat: Infinity,
                    ease: 'easeInOut',
                  }}
                  style={{
                    transform: 'translate(-50%, -50%)',
                  }}
                />

                {/* Glowing border pulse */}
                <motion.div 
                  className="absolute inset-0 rounded-[2.5rem] bg-gradient-to-r from-blue-500/0 via-blue-400/30 to-blue-500/0"
                  animate={{
                    opacity: [0, 1, 0],
                  }}
                  transition={{
                    duration: 3,
                    repeat: Infinity,
                    ease: 'easeInOut',
                  }}
                />
                
                {/* Floating rotating rings */}
                <motion.div
                  className="absolute -top-24 -right-24 w-48 h-48 border-[3px] border-blue-400/30 rounded-full"
                  animate={{ 
                    rotate: 360,
                    scale: [1, 1.3, 1],
                  }}
                  transition={{ 
                    rotate: { duration: 25, repeat: Infinity, ease: 'linear' },
                    scale: { duration: 4, repeat: Infinity },
                  }}
                  style={{ transformStyle: 'preserve-3d' }}
                />
                <motion.div
                  className="absolute -top-20 -right-20 w-40 h-40 border-[2px] border-blue-300/20 rounded-full"
                  animate={{ 
                    rotate: -360,
                    scale: [1, 1.2, 1],
                  }}
                  transition={{ 
                    rotate: { duration: 20, repeat: Infinity, ease: 'linear' },
                    scale: { duration: 3.5, repeat: Infinity },
                  }}
                />
                <motion.div
                  className="absolute -bottom-24 -left-24 w-48 h-48 border-[3px] border-blue-300/15 rounded-full"
                  animate={{ 
                    rotate: -360,
                    scale: [1, 1.4, 1],
                  }}
                  transition={{ 
                    rotate: { duration: 18, repeat: Infinity, ease: 'linear' },
                    scale: { duration: 5, repeat: Infinity },
                  }}
                />
                
                <div className="relative z-10 text-center">
                  <motion.div
                    animate={{ 
                      y: [0, -15, 0],
                      rotateZ: [0, 8, -8, 0],
                      rotateY: [0, 15, 0],
                    }}
                    transition={{ 
                      duration: 4,
                      repeat: Infinity,
                      ease: 'easeInOut',
                    }}
                    className="mb-12 inline-block"
                    style={{
                      filter: 'drop-shadow(0 0 30px rgba(59, 130, 246, 0.7))',
                    }}
                  >
                    <Lightbulb 
                      size={100} 
                      className="text-blue-300"
                      strokeWidth={1.5}
                    />
                  </motion.div>
                  
                  <motion.h2 
                    className="text-6xl font-bold mb-6 text-white drop-shadow-[0_0_30px_rgba(255,255,255,0.3)]"
                    style={{ transformStyle: 'preserve-3d' }}
                  >
                    DESIGN
                  </motion.h2>
                  <p className="text-2xl text-blue-100 font-light tracking-wide">Create tests</p>
                  
                  <motion.div
                    className="mt-12 text-base text-blue-300/80 font-medium"
                    animate={{ 
                      opacity: [0.5, 1, 0.5],
                      x: [0, 5, 0],
                    }}
                    transition={{ 
                      duration: 2.5, 
                      repeat: Infinity,
                      ease: 'easeInOut',
                    }}
                  >
                    Click to start →
                  </motion.div>
                </div>
              </div>
            </motion.div>

            {/* Execute Card */}
            <motion.div
              initial={{ opacity: 0, x: 150, rotateY: 25, scale: 0.8 }}
              animate={{ opacity: 1, x: 0, rotateY: 0, scale: 1 }}
              transition={{ 
                duration: 1.2, 
                delay: 0.8,
                type: 'spring',
                stiffness: 50,
              }}
              whileHover={{ 
                scale: 1.1, 
                y: -20,
                rotateY: -8,
                rotateX: 5,
                transition: { duration: 0.4 }
              }}
              whileTap={{ scale: 0.95 }}
              onClick={() => navigate('/dashboard')}
              className="relative group cursor-pointer"
              style={{ 
                perspective: '1500px',
                transformStyle: 'preserve-3d',
              }}
            >
              <div className="relative bg-gradient-to-br from-purple-900/50 to-pink-600/30 backdrop-blur-2xl border-2 border-purple-500/40 rounded-[2.5rem] p-16 overflow-hidden shadow-2xl shadow-purple-500/30 transition-all duration-700 group-hover:shadow-purple-400/60 group-hover:border-purple-400/60">
                {/* Animated glowing orb */}
                <motion.div
                  className="absolute top-1/2 left-1/2 w-64 h-64 bg-purple-500/20 rounded-full blur-3xl"
                  animate={{
                    scale: [1, 1.5, 1],
                    opacity: [0.3, 0.6, 0.3],
                  }}
                  transition={{
                    duration: 4,
                    repeat: Infinity,
                    ease: 'easeInOut',
                    delay: 0.5,
                  }}
                  style={{
                    transform: 'translate(-50%, -50%)',
                  }}
                />

                {/* Glowing border pulse */}
                <motion.div 
                  className="absolute inset-0 rounded-[2.5rem] bg-gradient-to-r from-purple-500/0 via-purple-400/30 to-purple-500/0"
                  animate={{
                    opacity: [0, 1, 0],
                  }}
                  transition={{
                    duration: 3,
                    repeat: Infinity,
                    ease: 'easeInOut',
                    delay: 0.5,
                  }}
                />
                
                {/* Floating rotating rings */}
                <motion.div
                  className="absolute -top-24 -right-24 w-48 h-48 border-[3px] border-purple-400/30 rounded-full"
                  animate={{ 
                    rotate: -360,
                    scale: [1, 1.3, 1],
                  }}
                  transition={{ 
                    rotate: { duration: 22, repeat: Infinity, ease: 'linear' },
                    scale: { duration: 4.5, repeat: Infinity },
                  }}
                />
                <motion.div
                  className="absolute -top-20 -right-20 w-40 h-40 border-[2px] border-purple-300/20 rounded-full"
                  animate={{ 
                    rotate: 360,
                    scale: [1, 1.2, 1],
                  }}
                  transition={{ 
                    rotate: { duration: 18, repeat: Infinity, ease: 'linear' },
                    scale: { duration: 4, repeat: Infinity },
                  }}
                />
                <motion.div
                  className="absolute -bottom-24 -left-24 w-48 h-48 border-[3px] border-pink-300/15 rounded-full"
                  animate={{ 
                    rotate: 360,
                    scale: [1, 1.4, 1],
                  }}
                  transition={{ 
                    rotate: { duration: 20, repeat: Infinity, ease: 'linear' },
                    scale: { duration: 5.5, repeat: Infinity },
                  }}
                />
                
                <div className="relative z-10 text-center">
                  <motion.div
                    animate={{ 
                      y: [0, -15, 0],
                      rotateZ: [0, -8, 8, 0],
                      rotateY: [0, -15, 0],
                    }}
                    transition={{ 
                      duration: 4,
                      repeat: Infinity,
                      ease: 'easeInOut',
                    }}
                    className="mb-12 inline-block"
                    style={{
                      filter: 'drop-shadow(0 0 30px rgba(168, 85, 247, 0.7))',
                    }}
                  >
                    <Play 
                      size={100} 
                      className="text-purple-300"
                      strokeWidth={1.5}
                      fill="currentColor"
                    />
                  </motion.div>
                  
                  <motion.h2 
                    className="text-6xl font-bold mb-6 text-white drop-shadow-[0_0_30px_rgba(255,255,255,0.3)]"
                    style={{ transformStyle: 'preserve-3d' }}
                  >
                    EXECUTE
                  </motion.h2>
                  <p className="text-2xl text-purple-100 font-light tracking-wide">Run suites</p>
                  
                  <motion.div
                    className="mt-12 text-base text-purple-300/80 font-medium"
                    animate={{ 
                      opacity: [0.5, 1, 0.5],
                      x: [0, 5, 0],
                    }}
                    transition={{ 
                      duration: 2.5, 
                      repeat: Infinity,
                      ease: 'easeInOut',
                      delay: 0.7,
                    }}
                  >
                    Click to start →
                  </motion.div>
                </div>
              </div>
            </motion.div>
          </div>

          {/* Floating sparkles */}
          <div className="absolute inset-0 pointer-events-none">
            {[...Array(20)].map((_, i) => (
              <motion.div
                key={`sparkle-${i}`}
                className="absolute w-1 h-1 bg-white rounded-full"
                style={{
                  left: `${Math.random() * 100}%`,
                  top: `${Math.random() * 100}%`,
                }}
                animate={{
                  opacity: [0, 1, 0],
                  scale: [0, 1.5, 0],
                }}
                transition={{
                  duration: 2 + Math.random() * 2,
                  repeat: Infinity,
                  delay: Math.random() * 3,
                }}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
