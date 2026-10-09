import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#0b0f15",
          900: "#0d1117",
          850: "#11161e",
          800: "#161c26",
          700: "#1e2633",
          600: "#2a3442",
        },
        line: "#263041",
        fg: { DEFAULT: "#d5dce6", muted: "#8592a4", dim: "#566173" },
        accent: "#ecad0a",
        primary: "#209dd7",
        secondary: "#753991",
        up: "#26b36b",
        down: "#e5484d",
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', "system-ui", "sans-serif"],
        cond: ['"IBM Plex Sans Condensed"', '"IBM Plex Sans"', "system-ui", "sans-serif"],
        num: ['"IBM Plex Mono"', "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
