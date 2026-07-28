import { create } from "zustand";

type AppState = {
  user: { name: string; email: string };
  approvalCount: number;
  setApprovalCount: (count: number) => void;
};

export const useAppStore = create<AppState>((set) => ({
  user: { name: "Ahmed Khan", email: "ahmed@company.com" },
  approvalCount: 7,
  setApprovalCount: (approvalCount) => set({ approvalCount }),
}));
