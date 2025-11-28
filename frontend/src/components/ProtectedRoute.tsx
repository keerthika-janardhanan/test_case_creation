import { Navigate, useLocation } from 'react-router-dom';
import { useAuthStore } from '../state/auth';

interface ProtectedRouteProps {
  children: React.ReactNode;
  requireAuth?: boolean;
  redirectTo?: string;
}

export function ProtectedRoute({ 
  children, 
  requireAuth = true, 
  redirectTo = '/login' 
}: ProtectedRouteProps) {
  const { isAuthenticated, isLoading } = useAuthStore();
  const location = useLocation();

  // TEMPORARY: Bypass authentication for demo/testing
  // TODO: Remove this and enable proper authentication
  const BYPASS_AUTH = true;

  // Show loading state while auth is being checked
  if (!BYPASS_AUTH && isLoading) {
    return (
      <div className="auth-loading">
        <div className="auth-loading-spinner">
          <div className="spinner"></div>
          <p>Checking authentication...</p>
        </div>
      </div>
    );
  }

  // Redirect unauthenticated users to login
  if (!BYPASS_AUTH && requireAuth && !isAuthenticated) {
    return (
      <Navigate 
        to={redirectTo} 
        state={{ from: location.pathname }} 
        replace 
      />
    );
  }

  // Redirect authenticated users away from auth pages
  if (!BYPASS_AUTH && !requireAuth && isAuthenticated) {
    const from = (location.state as any)?.from || '/';
    return <Navigate to={from} replace />;
  }

  return <>{children}</>;
}