import type { ReactElement } from "react";

import { Navigate } from "react-router-dom";

import type { Role } from "../state/session";
import { useSessionStore } from "../state/session";

interface ProtectedRouteProps {
  children: ReactElement;
  roles?: Role[];
}

export function ProtectedRoute({
  children,
  roles = [],
}: ProtectedRouteProps) {
  const role = useSessionStore((state) => state.role);

  if (roles.length && !roles.includes(role)) {
    return <Navigate to="/agentic" replace />;
  }

  return children;
}
