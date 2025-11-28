import { useState } from 'react';
import { VideoIcon, PlayIcon, LogOutIcon } from 'lucide-react';
import axios from 'axios';
import { toast, Toaster } from 'sonner';
import { useAuth } from '../hooks/useAuth';

const API_BASE = 'http://localhost:8000/api';

interface FormData {
  url: string;
  flowName: string;
  timer: number;
}

export default function Dashboard() {
  const [showForm, setShowForm] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const { logout, userName } = useAuth();
  const [formData, setFormData] = useState<FormData>({
    url: 'https://example.com',
    flowName: 'e.g., Login Flow',
    timer: 30
  });

  const handleStartRecording = async () => {
    if (!formData.url || !formData.flowName) {
      toast.error('Please fill in URL and Flow Name');
      return;
    }

    setIsLoading(true);
    try {
      const response = await axios.post(`${API_BASE}/start-recording`, {
        url: formData.url,
        flow_name: formData.flowName,
        timeout: formData.timer
      });
      toast.success('Recording started successfully!');
      console.log('Recording session:', response.data);
    } catch (error) {
      toast.error('Failed to start recording');
      console.error('Recording error:', error);
    } finally {
      setIsLoading(false);
    }
  };

  if (showForm) {
    return (
      <div className="dashboard-container">
        <Toaster position="top-right" />
        
        {/* Floating Background Shapes */}
        <div className="floating-shapes">
          <div className="shape shape-1"></div>
          <div className="shape shape-2"></div>
          <div className="shape shape-3"></div>
        </div>

        <div className="dashboard-content">
          {/* Header */}
          <div style={{ textAlign: 'center', marginBottom: '3rem' }}>
            <div style={{ 
              display: 'inline-flex', 
              alignItems: 'center', 
              gap: '12px', 
              marginBottom: '1rem' 
            }}>
              <div style={{
                width: '50px',
                height: '50px',
                background: 'linear-gradient(135deg, #a855f7, #ec4899)',
                borderRadius: '12px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: '0 8px 32px rgba(168, 85, 247, 0.3)'
              }}>
                ✨
              </div>
              <h1 style={{ 
                fontSize: '2rem', 
                fontWeight: '700', 
                color: 'white',
                margin: 0,
                fontFamily: 'Fredoka'
              }}>
                Test Automation Studio
              </h1>
            </div>
            <p style={{ 
              color: 'rgba(255, 255, 255, 0.8)', 
              fontSize: '1rem',
              margin: 0
            }}>
              Record • Generate • Automate ✨
            </p>
          </div>

          {/* Recording Form */}
          <div style={{ 
            display: 'flex', 
            justifyContent: 'center', 
            alignItems: 'center',
            minHeight: '50vh'
          }}>
            <div className="card" style={{ 
              maxWidth: '500px',
              width: '100%',
              background: 'rgba(255, 255, 255, 0.95)'
            }}>
              <div style={{ 
                display: 'flex', 
                alignItems: 'center', 
                gap: '12px', 
                marginBottom: '1.5rem' 
              }}>
                <VideoIcon size={24} color="#8b5cf6" />
                <h2 style={{ 
                  fontSize: '1.5rem', 
                  color: '#1f2937',
                  margin: 0,
                  fontWeight: '600'
                }}>
                  Start Recording
                </h2>
              </div>
              
              <p style={{ 
                color: '#6b7280', 
                marginBottom: '2rem' 
              }}>
                Configure your screen recording settings
              </p>

              <div style={{ marginBottom: '1.5rem' }}>
                <label style={{ 
                  display: 'block', 
                  marginBottom: '0.5rem', 
                  fontWeight: '500',
                  color: '#374151'
                }}>
                  URL
                </label>
                <input
                  type="text"
                  value={formData.url}
                  onChange={(e) => setFormData({...formData, url: e.target.value})}
                  placeholder="https://example.com"
                  style={{ marginBottom: '0' }}
                />
              </div>

              <div style={{ marginBottom: '1.5rem' }}>
                <label style={{ 
                  display: 'block', 
                  marginBottom: '0.5rem', 
                  fontWeight: '500',
                  color: '#374151'
                }}>
                  Flow Name
                </label>
                <input
                  type="text"
                  value={formData.flowName}
                  onChange={(e) => setFormData({...formData, flowName: e.target.value})}
                  placeholder="e.g., Login Flow"
                  style={{ marginBottom: '0' }}
                />
              </div>

              <div style={{ marginBottom: '2rem' }}>
                <label style={{ 
                  display: 'block', 
                  marginBottom: '0.5rem', 
                  fontWeight: '500',
                  color: '#374151'
                }}>
                  Timer (seconds)
                </label>
                <input
                  type="number"
                  value={formData.timer}
                  onChange={(e) => setFormData({...formData, timer: parseInt(e.target.value) || 30})}
                  min="10"
                  max="300"
                  style={{ marginBottom: '0' }}
                />
              </div>

              <div style={{ 
                display: 'flex', 
                gap: '12px', 
                justifyContent: 'flex-end' 
              }}>
                <button 
                  className="btn"
                  onClick={() => setShowForm(false)}
                  style={{
                    background: '#6b7280',
                    padding: '12px 24px'
                  }}
                >
                  Cancel
                </button>
                <button 
                  className="btn"
                  onClick={handleStartRecording}
                  disabled={isLoading}
                  style={{
                    padding: '12px 24px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    opacity: isLoading ? 0.7 : 1
                  }}
                >
                  <PlayIcon size={16} />
                  {isLoading ? 'Starting...' : 'Start Recording'}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="dashboard-container">
      <Toaster position="top-right" />
      
      {/* Floating Background Shapes */}
      <div className="floating-shapes">
        <div className="shape shape-1"></div>
        <div className="shape shape-2"></div>
        <div className="shape shape-3"></div>
      </div>

      <div className="dashboard-content">
        {/* User Header */}
        <div className="user-header">
          <span className="welcome-text">Welcome, {userName}!</span>
          <button 
            onClick={logout} 
            className="logout-btn"
            title="Sign out"
          >
            <LogOutIcon size={18} />
            Sign Out
          </button>
        </div>

        {/* Header */}
        <div style={{ textAlign: 'center', marginBottom: '3rem' }}>
          <div style={{ 
            display: 'inline-flex', 
            alignItems: 'center', 
            gap: '12px', 
            marginBottom: '1rem' 
          }}>
            <div style={{
              width: '50px',
              height: '50px',
              background: 'linear-gradient(135deg, #a855f7, #ec4899)',
              borderRadius: '12px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: '0 8px 32px rgba(168, 85, 247, 0.3)'
            }}>
              ✨
            </div>
            <h1 style={{ 
              fontSize: '2rem', 
              fontWeight: '700', 
              color: 'white',
              margin: 0,
              fontFamily: 'Fredoka'
            }}>
              Test Automation Studio
            </h1>
          </div>
          <p style={{ 
            color: 'rgba(255, 255, 255, 0.8)', 
            fontSize: '1rem',
            margin: 0
          }}>
            Record • Generate • Automate ✨
          </p>
        </div>

        {/* Main Welcome Card */}
        <div style={{ 
          display: 'flex', 
          justifyContent: 'center', 
          alignItems: 'center',
          minHeight: '60vh'
        }}>
          <div className="card" style={{ 
            textAlign: 'center', 
            maxWidth: '600px',
            background: 'rgba(255, 255, 255, 0.95)',
            transform: 'scale(1)',
            transition: 'all 0.3s ease'
          }}>
            <h2 style={{ 
              fontSize: '2.2rem', 
              marginBottom: '1rem', 
              color: '#1f2937',
              fontFamily: 'Fredoka'
            }}>
              Let's Get Started!
            </h2>
            <p style={{ 
              color: '#6b7280', 
              fontSize: '1.1rem', 
              marginBottom: '2.5rem' 
            }}>
              Click below to begin your journey
            </p>
            
            <div style={{ 
              display: 'flex', 
              flexDirection: 'column', 
              alignItems: 'center', 
              gap: '2rem' 
            }}>
              <div style={{
                width: '120px',
                height: '120px',
                background: 'linear-gradient(135deg, #8b5cf6, #ec4899)',
                borderRadius: '24px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: '0 20px 40px rgba(139, 92, 246, 0.3)',
                animation: 'float 3s ease-in-out infinite',
                cursor: 'pointer',
                transition: 'transform 0.3s ease'
              }}
              onMouseEnter={(e) => e.currentTarget.style.transform = 'scale(1.05)'}
              onMouseLeave={(e) => e.currentTarget.style.transform = 'scale(1)'}
              >
                <VideoIcon size={50} color="white" />
              </div>
              
              <div>
                <h3 style={{ 
                  fontSize: '1.5rem', 
                  marginBottom: '0.5rem', 
                  color: '#1f2937',
                  fontWeight: '600'
                }}>
                  Recordings
                </h3>
                <p style={{ 
                  color: '#6b7280', 
                  marginBottom: '1.5rem' 
                }}>
                  Start a new screen recording session
                </p>
                
                <button 
                  className="btn"
                  onClick={() => setShowForm(true)}
                  style={{
                    fontSize: '1.1rem',
                    padding: '16px 32px',
                    borderRadius: '50px',
                    background: 'linear-gradient(135deg, #8b5cf6, #ec4899)',
                    border: 'none',
                    color: 'white',
                    fontWeight: '600',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    margin: '0 auto',
                    transition: 'all 0.3s ease'
                  }}
                >
                  Click to Start
                  <PlayIcon size={20} />
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}