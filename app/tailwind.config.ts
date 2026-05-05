import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Xiexie palette — warm, calm, slightly amber (the "hearth" feel)
        ember: {
          50: "#fdf7ee",
          100: "#fae8ce",
          200: "#f4cf99",
          300: "#ecb066",
          400: "#e3963f",
          500: "#d97a25",
          600: "#bd5e1d",
          700: "#9b461c",
          800: "#7a371c",
          900: "#5e2c19",
        },
      },
      fontFamily: {
        sans: ["ui-sans-serif", "system-ui", "-apple-system", "sans-serif"],
      },
      // Senior-friendly type scale — bumped 1 step from default.
      fontSize: {
        base: ["1.125rem", { lineHeight: "1.75rem" }],
        lg: ["1.25rem", { lineHeight: "1.875rem" }],
        xl: ["1.5rem", { lineHeight: "2rem" }],
        "2xl": ["1.875rem", { lineHeight: "2.375rem" }],
      },
    },
  },
  plugins: [],
};

export default config;
