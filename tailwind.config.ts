import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0B1120",
        surface: "#111827",
        "surface-2": "#1A2D52",
        border: "#1E3A6E",
        "border-strong": "#2D5099",
        accent: "#2D7DD2",
        teal: "#0D9488",
        success: "#10B981",
        warning: "#F59E0B",
        danger: "#EF4444",
        purple: "#7C3AED",
        primary: "#F1F5F9",
        secondary: "#94A3B8",
        muted: "#475569"
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular"]
      },
      borderRadius: {
        sm: "6px",
        md: "10px",
        lg: "16px"
      },
      boxShadow: {
        card: "0 1px 3px rgba(0,0,0,0.4), 0 0 0 1px #1E3A6E",
        modal: "0 8px 32px rgba(0,0,0,0.6), 0 0 0 1px #2D5099",
        glow: "0 0 20px rgba(45,125,210,0.15)"
      }
    }
  },
  plugins: []
} satisfies Config;
