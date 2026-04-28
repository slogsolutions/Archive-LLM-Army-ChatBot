/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,jsx}",
    "./components/**/*.{js,jsx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        sidebar: "#202123",
        chat:    "#343541",
        input:   "#40414f",
        border:  "#4d4d4f",
        accent:  "#10a37f",
      },
    },
  },
  plugins: [],
};
