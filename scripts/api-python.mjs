// Runs apps/api's virtualenv Python with the given arguments, on Windows or POSIX.
// Usage: node scripts/api-python.mjs -m uvicorn app.main:app --reload
import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
import { join } from 'node:path'

const apiDir = join(import.meta.dirname, '..', 'apps', 'api')
const python =
  process.platform === 'win32'
    ? join(apiDir, '.venv', 'Scripts', 'python.exe')
    : join(apiDir, '.venv', 'bin', 'python')

if (!existsSync(python)) {
  console.error(`No virtualenv found at ${python}. Run the setup steps in README.md first.`)
  process.exit(1)
}

const child = spawn(python, process.argv.slice(2), { cwd: apiDir, stdio: 'inherit' })
child.on('exit', (code) => process.exit(code ?? 1))
