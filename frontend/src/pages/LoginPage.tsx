import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { LogInIcon, EyeIcon, EyeOffIcon, LoaderIcon } from 'lucide-react';
import { useAuth } from '../hooks/useAuth';
import { toast, Toaster } from 'sonner';

export default function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(false);
  
  const { login, isLoading, error, isAuthenticated, clearError } = useAuth();
  const navigate = useNavigate();

  // Redirect if already authenticated
  useEffect(() => {
    if (isAuthenticated) {
      navigate('/', { replace: true });
    }
  }, [isAuthenticated, navigate]);

  // Show error toast when error changes
  useEffect(() => {
    if (error) {
      toast.error(error);
      clearError();
    }
  }, [error, clearError]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!email.trim()) {
      toast.error('Email is required');
      return;
    }
    
    if (!password.trim()) {
      toast.error('Password is required');
      return;
    }

    try {
      await login(email, password);
      toast.success('Welcome back!');
    } catch (err) {
      // Error handling is done in the store and shown via toast
    }
  };

  return (
    <div className="login-container">
      <Toaster position="top-right" />
      
      {/* Floating Background Shapes */}
      <div className="floating-shapes">
        <div className="shape shape-1"></div>
        <div className="shape shape-2"></div>
        <div className="shape shape-3"></div>
      </div>

      <div className="login-content">
        <div className="login-card">
          {/* Logo/Brand */}
          <div className="login-header">
            <div className="login-logo">
              <div className="logo-icon">
                ✨
              </div>
              <h1 className="brand-title">
                Test Automation Studio
              </h1>
            </div>
            <p className="brand-subtitle">
              Welcome back! Please sign in to your account
            </p>
          </div>

          {/* Login Form */}
          <form onSubmit={handleSubmit} className="login-form">
            {/* Email Field */}
            <div className="form-group">
              <label htmlFor="email" className="form-label">
                Email Address
              </label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="Enter your email"
                className="form-input"
                autoComplete="email"
                disabled={isLoading}
              />
            </div>

            {/* Password Field */}
            <div className="form-group">
              <label htmlFor="password" className="form-label">
                Password
              </label>
              <div className="password-input-wrapper">
                <input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter your password"
                  className="form-input password-input"
                  autoComplete="current-password"
                  disabled={isLoading}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="password-toggle"
                  disabled={isLoading}
                >
                  {showPassword ? <EyeOffIcon size={18} /> : <EyeIcon size={18} />}
                </button>
              </div>
            </div>

            {/* Remember Me & Forgot Password */}
            <div className="form-options">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={rememberMe}
                  onChange={(e) => setRememberMe(e.target.checked)}
                  disabled={isLoading}
                />
                <span className="checkbox-text">Remember me</span>
              </label>
              <button type="button" className="forgot-password-link" disabled={isLoading}>
                Forgot password?
              </button>
            </div>

            {/* Submit Button */}
            <button
              type="submit"
              disabled={isLoading}
              className="login-button"
            >
              {isLoading ? (
                <>
                  <LoaderIcon size={18} className="spinner" />
                  Signing in...
                </>
              ) : (
                <>
                  <LogInIcon size={18} />
                  Sign In
                </>
              )}
            </button>
          </form>

          {/* Demo Credentials */}
          <div className="demo-credentials">
            <p className="demo-title">Demo Credentials:</p>
            <p className="demo-text">
              Email: <strong>demo@example.com</strong><br />
              Password: <strong>demo123</strong>
            </p>
          </div>

          {/* Footer */}
          <div className="login-footer">
            <p>
              Don't have an account?{' '}
              <button type="button" className="signup-link">
                Sign up
              </button>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}