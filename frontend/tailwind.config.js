/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#1c1917",
        paper: "#f6f1e8",
        cream: "#fffdf8",
        navy: "#1e3a5f",
        navydeep: "#152a46",
        brass: "#9a6b2f",
        rule: "#ddd4c4",
      },
      fontFamily: {
        serif: ['"Palatino Linotype"', "Palatino", "Georgia", "serif"],
        sans: ['"Segoe UI"', '"Noto Sans"', '"Noto Sans Kannada"', "sans-serif"],
      },
    },
  },
  plugins: [],
};
