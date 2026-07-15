import type { Config } from "tailwindcss"

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        sidebar: {
          DEFAULT: '#1a1b2e',
          hover: '#252640',
          active: '#2d2e4a',
        },
        chat: {
          bg: '#0f1017',
          user: '#2b2d42',
          assistant: '#1e1f33',
          input: '#1a1b2e',
        },
        accent: {
          DEFAULT: '#6c63ff',
          hover: '#5a52e0',
        }
      },
    },
  },
  plugins: [],
}
export default config
