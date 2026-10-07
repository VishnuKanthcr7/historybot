/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#252525",
        paper: "#F7F4EE",
        cream: "#FFFDF8",
        navy: "#7A3E2B",
        navydeep: "#5C2E20",
        brass: "#B88A44",
        rule: "#E7DED0",
        muted: "#6F6A63",
      },
      fontFamily: {
        serif: ['"Playfair Display"', "Georgia", "serif"],
        sans: ["Inter", '"Noto Sans Kannada"', '"Segoe UI"', "sans-serif"],
      },
      screens: {
        xs: "375px",
      },
    },
  },
  plugins: [],
};
