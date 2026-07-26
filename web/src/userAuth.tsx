import { createContext, useContext, useState, useEffect, ReactNode } from "react";

interface PortalUser {
  id: number;
  email: string;
  name: string | null;
  credits_usd?: number;
}

interface UserAuthContextType {
  token: string | null;
  user: PortalUser | null;
  isAuthenticated: boolean;
  login: (token: string, user: PortalUser) => void;
  logout: () => void;
}

const UserAuthContext = createContext<UserAuthContextType>({
  token: null,
  user: null,
  isAuthenticated: false,
  login: () => {},
  logout: () => {},
});

export function UserAuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<PortalUser | null>(null);

  useEffect(() => {
    const saved = localStorage.getItem("swiftgate_user_token");
    const savedUser = localStorage.getItem("swiftgate_user");
    if (saved && savedUser) {
      setToken(saved);
      try {
        setUser(JSON.parse(savedUser));
      } catch {
        localStorage.removeItem("swiftgate_user_token");
        localStorage.removeItem("swiftgate_user");
      }
    }
  }, []);

  const login = (newToken: string, newUser: PortalUser) => {
    localStorage.setItem("swiftgate_user_token", newToken);
    localStorage.setItem("swiftgate_user", JSON.stringify(newUser));
    setToken(newToken);
    setUser(newUser);
  };

  const logout = () => {
    localStorage.removeItem("swiftgate_user_token");
    localStorage.removeItem("swiftgate_user");
    setToken(null);
    setUser(null);
  };

  return (
    <UserAuthContext.Provider
      value={{ token, user, isAuthenticated: !!token, login, logout }}
    >
      {children}
    </UserAuthContext.Provider>
  );
}

export function useUserAuth() {
  return useContext(UserAuthContext);
}

/**
 * fetch() wrapper that auto-injects the user JWT bearer token.
 */
export function userFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const token = localStorage.getItem("swiftgate_user_token");
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return fetch(url, { ...options, headers });
}
