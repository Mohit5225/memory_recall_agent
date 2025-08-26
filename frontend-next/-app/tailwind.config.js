/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      maxWidth: {
        '2.0': '2.0rem',
        '2.1': '2.1rem',
        '2.2': '2.2rem',
        '2.3': '2.3rem',
        '2.4': '2.4rem',
        '2.5': '2.5rem',
        '2.6': '2.6rem',
      },
    },
  },
  plugins: [],
}