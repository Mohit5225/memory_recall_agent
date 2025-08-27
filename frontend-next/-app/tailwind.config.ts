import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    // These paths are now correct and specific.
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      // Your custom maxWidth values are safe.
      maxWidth: {
        '2.0': '2.0rem',
        '2.1': '2.1rem',
        '2.2': '2.2rem',
        '2.3': '2.3rem',
        '2.4': '2.4rem',
        '2.5': '2.5rem',
        '2.6': '2.6rem',
      },
      // And our font family is still perfect.
      fontFamily: {
        sans: ["var(--font-lato)"],
      },
    },
  },
  plugins: [],
};
export default config;