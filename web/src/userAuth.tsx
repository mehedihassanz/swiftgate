import { createContext, useContext, useState, useEffect, ReactNode } from "react";

interface PortalUser {
  id: number;
  email: string;
  name: string | null;
  credits_usd?: number;
  is_admin?: boolean;
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
      // Verify token is still valid by calling /auth/me
      fetch("/auth/me", {
        headers: { Authorization: `Bearer ${saved}` },
      })
        .then((r) => {
          if (r.ok) return r.json();
          // Token expired or invalid — clear it
          localStorage.removeItem("swiftgate_user_token");
          localStorage.removeItem("swiftgate_user");
          return null;
        })
        .then((data) => {
          if (data) {
            setToken(saved);
            setUser(data);
          }
        })
        .catch(() => {
          // Network error — keep token, might work later
          try {
            setToken(saved);
            setUser(JSON.parse(savedUser));
          } catch {
            localStorage.removeItem("swiftgate_user_token");
            localStorage.removeItem("swiftgate_user");
          }
        });
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
 * On 401, clears the token and redirects to login.
 */
export async function userFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const token = localStorage.getItem("swiftgate_user_token");
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const resp = await fetch(url, { ...options, headers });
  if (resp.status === 401) {
    localStorage.removeItem("swiftgate_user_token");
    localStorage.removeItem("swiftgate_user");
    window.location.href = "/portal/login";
  }
  return resp;
}
