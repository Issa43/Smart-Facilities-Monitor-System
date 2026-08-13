import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  css: {
    modules: {
      // Write kebab-case in .module.css, consume camelCase in TSX: styles.kpiCard
      localsConvention: 'camelCaseOnly',
    },
  },
  server: {
    // Open the browser automatically so `npm run dev` is the only step needed.
    open: true,
  },
})
