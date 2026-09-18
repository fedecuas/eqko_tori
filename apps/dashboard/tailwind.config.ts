import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Paleta oficial EQKO (mismos swatches que el dashboard de Jarvis).
        navy: "#0E1C2D",
        sky: "#28ABE3",
        orange: "#BB5624",
        lime: "#6E8A0E",
        red: "#D11C17",
        purple: "#4F4394",
        charcoal: "#2F2F30",
        offwhite: "#F1EDEE",
      },
    },
  },
  plugins: [],
};

export default config;
