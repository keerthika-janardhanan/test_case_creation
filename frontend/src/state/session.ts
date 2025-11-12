import { create } from "zustand";

export type Role = "user" | "admin";

type SessionState = {
  role: Role;
  frameworkRepoPath: string;
  frameworkBranch: string;
  frameworkCommitMessage: string;
  authToken: string;
  setRole: (role: Role) => void;
  setFrameworkRepoPath: (path: string) => void;
  setFrameworkBranch: (branch: string) => void;
  setFrameworkCommitMessage: (message: string) => void;
  setAuthToken: (token: string) => void;
};

export const useSessionStore = create<SessionState>((set) => ({
  role: "user",
  frameworkRepoPath: "",
  frameworkBranch: "main",
  frameworkCommitMessage: "Add generated Playwright test",
  authToken: "dev",
  setRole: (role) => set({ role }),
  setFrameworkRepoPath: (frameworkRepoPath) => set({ frameworkRepoPath }),
  setFrameworkBranch: (frameworkBranch) => set({ frameworkBranch }),
  setFrameworkCommitMessage: (frameworkCommitMessage) =>
    set({ frameworkCommitMessage }),
  setAuthToken: (authToken) => set({ authToken }),
}));

