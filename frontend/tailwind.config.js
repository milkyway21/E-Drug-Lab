/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/lib/**/*.{js,ts,jsx,tsx,mdx}"
  ],
  theme: {
    extend: {
      colors: {
        ink: "#1a2332",
        muted: "#5a6a7a",
        mist: "#f0f4f8",
        paper: "#ffffff",
        primary: {
          DEFAULT: "#1565C0",
          50: "#E3F2FD",
          100: "#BBDEFB",
          200: "#90CAF9",
          300: "#64B5F6",
          400: "#42A5F5",
          500: "#1565C0",
          600: "#0D47A1",
          700: "#0A3D8F",
          800: "#07337D",
          900: "#04296B",
        },
        teal: {
          DEFAULT: "#00897B",
          light: "#4DB6AC",
          dark: "#00695C",
        },
        cobalt: {
          DEFAULT: "#1565C0",
          light: "#42A5F5",
          dark: "#0D47A1",
        },
        amber: {
          DEFAULT: "#F9A825",
          light: "#FDD835",
          dark: "#F57F17",
        },
        rose: {
          DEFAULT: "#C62828",
          light: "#EF5350",
          dark: "#B71C1C",
        },
        success: "#2E7D32",
        warning: "#F57F17",
        danger: "#C62828",
        slate: {
          50: "#F8FAFB",
          100: "#EEF2F5",
          150: "#E5EBF0",
          200: "#D5DDE5",
          300: "#B0BEC5",
          400: "#90A4AE",
          500: "#78909C",
          600: "#607D8B",
          700: "#546E7A",
          800: "#37474F",
          900: "#263238",
        },
      },
      fontFamily: {
        display: ['"Outfit"', "system-ui", "sans-serif"],
        body: ['"Plus Jakarta Sans"', "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "monospace"],
      },
      boxShadow: {
        panel: "0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04)",
        soft: "0 1px 2px rgba(0,0,0,0.04)",
        elevated: "0 4px 16px rgba(0,0,0,0.08), 0 1px 3px rgba(0,0,0,0.06)",
        card: "0 1px 4px rgba(21,101,192,0.06), 0 0 0 1px rgba(21,101,192,0.04)",
      },
      animation: {
        "fade-in": "fadeIn 0.4s ease-out forwards",
        "slide-up": "slideUp 0.4s ease-out forwards",
        "slide-in-right": "slideInRight 0.35s ease-out forwards",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        slideUp: {
          "0%": { opacity: "0", transform: "translateY(12px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        slideInRight: {
          "0%": { opacity: "0", transform: "translateX(16px)" },
          "100%": { opacity: "1", transform: "translateX(0)" },
        },
      },
    }
  },
  plugins: []
};
