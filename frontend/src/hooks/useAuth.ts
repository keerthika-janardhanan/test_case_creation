import { useAuthStore } from '../state/auth';
import { useNavigate } from 'react-router-dom';
import { useCallback } from 'react';
import { toast } from 'sonner';

/**
 * Custom hook for authentication operations
 * Provides easy access to auth state and actions
 */
export function useAuth() {
  const {
    user,
    token,
    isAuthenticated,
    isLoading,
    error,
    login,
    logout,
    clearError,
    setError
  } = useAuthStore();
  
  const navigate = useNavigate();

  const handleLogin = useCallback(async (email: string, password: string) => {
    try {
      await login(email, password);
      // Navigation is handled by the ProtectedRoute component
      return true;
    } catch (error) {
      console.error('Login failed:', error);
      return false;
    }
  }, [login]);

  const handleLogout = useCallback(() => {
    logout();
    navigate('/login', { replace: true });
    toast.success('You have been logged out successfully');
  }, [logout, navigate]);

  const handleClearError = useCallback(() => {
    clearError();
  }, [clearError]);

  // Check if user has specific role
  const hasRole = useCallback((role: string) => {
    return user?.role === role;
  }, [user]);

  // Check if user has any of the specified roles
  const hasAnyRole = useCallback((roles: string[]) => {
    return user?.role ? roles.includes(user.role) : false;
  }, [user]);

  return {
    // State
    user,
    token,
    isAuthenticated,
    isLoading,
    error,
    
    // Actions
    login: handleLogin,
    logout: handleLogout,
    clearError: handleClearError,
    setError,
    
    // Utilities
    hasRole,
    hasAnyRole,
    
    // User info
    userName: user?.name || '',
    userEmail: user?.email || '',
    userRole: user?.role || ''
  };
}