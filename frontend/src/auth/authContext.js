import { createContext, useContext } from "react";

// Shared auth context so any component (e.g. the top bar) can read the current user and sign out.
export const AuthContext = createContext({
  user: null,          // { name, username }
  logout: () => {},
});

export function useAuth() {
  return useContext(AuthContext);
}
