import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        wechat: {
          bg: '#ededed',
          green: '#95ec69',
          white: '#ffffff',
          dark: '#191919',
          gray: '#888888',
          light: '#f5f5f5',
        },
      },
      maxWidth: {
        mobile: '480px',
      },
    },
  },
  plugins: [],
};

export default config;
