// Starts the Vite dev server on a given port, proxying /api to a given API, on any shell.
// Usage: node scripts/web-dev.mjs <port> <api target>   (used by `npm run e2e`)
import { spawn } from 'node:child_process'
import { join } from 'node:path'

const [port = '5173', apiTarget = 'http://127.0.0.1:8000'] = process.argv.slice(2)
const child = spawn(`npx vite --port ${port} --strictPort`, {
  cwd: join(import.meta.dirname, '..', 'apps', 'web'),
  env: { ...process.env, API_PROXY_TARGET: apiTarget },
  shell: true,
  stdio: 'inherit',
})
child.on('exit', (code) => process.exit(code ?? 1))
