import { createContext, useContext, useState, useEffect, ReactNode } from "react";

interface AuthContextType {
  adminKey: string | null;
  isAuthenticated: boolean;
  login: (key: string) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType>({
  adminKey: null,
  isAuthenticated: false,
  login: () => {},
  logout: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [adminKey, setAdminKey] = useState<string | null>(null);

  useEffect(() => {
    const stored = localStorage.getItem("swiftgate_admin_key");
    if (stored) setAdminKey(stored);
  }, []);

  const login = (key: string) => {
    localStorage.setItem("swiftgate_admin_key", key);
    setAdminKey(key);
  };

  const logout = () => {
    localStorage.removeItem("swiftgate_admin_key");
    setAdminKey(null);
  };

  return (
    <AuthContext.Provider
      value={{ adminKey, isAuthenticated: !!adminKey, login, logout }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}

/**
 * Wrapper around fetch() that auto-injects the admin key header.
 * Use this for all admin/management API calls.
 */
export function authFetch(
  url: string,
  options: RequestInit = {},
): Promise<Response> {
  const key = localStorage.getItem("swiftgate_admin_key");
  const headers = new Headers(options.headers);
  if (key) headers.set("X-Admin-Key", key);
  return fetch(url, { ...options, headers });
}
