import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0B1020",
        canvas: "#F6F7F9",
        action: "#4F46E5",
        healthy: "#166534",
        "healthy-bg": "#DCFCE7",
        warning: "#B45309",
        "warning-bg": "#FEF3C7",
        critical: "#B91C1C",
        "critical-bg": "#FEE2E2",
      },
      fontFamily: {
        sans: ["var(--font-inter)", "ui-sans-serif", "system-ui", "sans-serif"],
        heading: ["var(--font-grotesk)", "ui-sans-serif", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
export default config;
