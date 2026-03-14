/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'chat-bg': '#212121',     // [cite: 385]
        'sidebar-bg': '#171717',  // [cite: 385]
        'input-bg': '#2f2f2f',    // [cite: 386]
        'bot-green': '#10a37f'    // [cite: 382]
      }
    },
  },
  plugins: [],
}