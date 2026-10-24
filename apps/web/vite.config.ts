import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// The config runs in Node; declared here instead of adding @types/node for one variable.
declare const process: { env: Record<string, string | undefined> }

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // API_PROXY_TARGET lets a second dev stack run alongside (e.g. the e2e click-through).
    proxy: { '/api': process.env.API_PROXY_TARGET ?? 'http://127.0.0.1:8000' },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
  },
})
