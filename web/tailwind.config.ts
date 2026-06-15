import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        navy: {
          950: "#0a0f1f",
          900: "#0d1428",
          800: "#131c36",
          700: "#1b2747",
        },
      },
    },
  },
  plugins: [],
};

export default config;
