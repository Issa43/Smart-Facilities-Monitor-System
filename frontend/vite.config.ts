import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  test: {
    setupFiles: './src/test/setup.ts',
    exclude: ['e2e/**', 'node_modules/**', 'dist/**'],
  },
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
    // The backend's CORS allow-list names this exact origin. Vite's default is
    // to take the next free port when 5173 is busy, which silently moves the
    // app to an origin the API rejects: the page still loads (Vite serves it
    // same-origin) but every request fails the preflight. Refusing to start is
    // far easier to diagnose than that, and it names the stale dev server.
    port: 5173,
    strictPort: true,
  },
})
