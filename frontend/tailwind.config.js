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
        ink: "#172026",
        muted: "#52616b",
        mist: "#eef4f3",
        paper: "#fbfcfb",
        teal: "#168575",
        cobalt: "#315fae",
        amber: "#c87d17",
        rose: "#b8485f"
      },
      boxShadow: {
        panel: "0 18px 45px rgba(23, 32, 38, 0.08)",
        soft: "0 8px 24px rgba(23, 32, 38, 0.06)"
      }
    }
  },
  plugins: []
};
