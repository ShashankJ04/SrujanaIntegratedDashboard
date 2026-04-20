import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { apiFetch, getAuthToken, setAuthToken } from "../api/client";
import type { Permissions } from "./permissions";

interface AuthUser {
  id: number;
  login: string;
  firstName: string;
  lastName: string;
  isAdmin: boolean;
}

interface AuthContextValue {
  user: AuthUser | null;
  permissions: Permissions | null;
  loading: boolean;
  login: (login: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

function decodeJwtPayload(token: string): { exp?: number } | null {
  const parts = token.split(".");
  if (parts.length !== 3) return null;
  const payload = parts[1].replace(/-/g, "+").replace(/_/g, "/");
  try {
    const decoded = atob(payload.padEnd(Math.ceil(payload.length / 4) * 4, "="));
    return JSON.parse(decoded) as { exp?: number };
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [permissions, setPermissions] = useState<Permissions | null>(null);
  const [loading, setLoading] = useState(true);
  const [token, setToken] = useState<string | null>(() => getAuthToken());
  const logoutTimer = useRef<number | null>(null);

  const logout = useCallback(() => {
    setAuthToken(null);
    setToken(null);
    setUser(null);
    setPermissions(null);
    setLoading(false);
  }, []);

  const scheduleLogout = useCallback((rawToken: string | null) => {
    if (logoutTimer.current) {
      window.clearTimeout(logoutTimer.current);
      logoutTimer.current = null;
    }

    if (!rawToken) return;
    const payload = decodeJwtPayload(rawToken);
    const exp = payload?.exp ? payload.exp * 1000 : null;
    if (!exp) return;
    const delay = exp - Date.now();
    if (delay <= 0) {
      logout();
      return;
    }
    logoutTimer.current = window.setTimeout(() => logout(), delay);
  }, [logout]);

  const loadCurrentUser = useCallback(async () => {
    if (!token) {
      setLoading(false);
      return;
    }

    setLoading(true);
    try {
      const res = await apiFetch<{ user: AuthUser; permissions: Permissions }>("/api/auth/me");
      setUser(res.user);
      setPermissions(res.permissions);
    } catch {
      logout();
    } finally {
      setLoading(false);
    }
  }, [token, logout]);

  useEffect(() => {
    scheduleLogout(token);
    loadCurrentUser();
  }, [token, scheduleLogout, loadCurrentUser]);

  useEffect(() => {
    const handler = () => logout();
    window.addEventListener("auth:logout", handler);
    return () => window.removeEventListener("auth:logout", handler);
  }, [logout]);

  const login = useCallback(async (loginValue: string, password: string) => {
    const res = await apiFetch<{ token: string; user: AuthUser; permissions: Permissions }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ login: loginValue, password }),
    });

    setAuthToken(res.token);
    setToken(res.token);
    setUser(res.user);
    setPermissions(res.permissions);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ user, permissions, loading, login, logout }),
    [user, permissions, loading, login, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return ctx;
}
