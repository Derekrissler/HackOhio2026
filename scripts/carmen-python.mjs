// Runs the Carmen mock Canvas virtualenv Python (carmen-study-guide/mock-canvas) with the given arguments.
// Usage: node scripts/carmen-python.mjs -m uvicorn server:app --port 8001
// If the virtualenv is missing it says how to create it and exits cleanly, so `npm run dev` keeps the API and web up.
import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
import { join } from 'node:path'

const carmenDir = join(import.meta.dirname, '..', 'carmen-study-guide', 'mock-canvas')
const python =
  process.platform === 'win32'
    ? join(carmenDir, '.venv', 'Scripts', 'python.exe')
    : join(carmenDir, '.venv', 'bin', 'python')

if (!existsSync(python)) {
  console.error(`Carmen (mock Canvas + Study Tutor) is not set up, so it was skipped. To add it:
  py -3 -m venv carmen-study-guide/mock-canvas/.venv     (macOS/Linux: python3 -m venv ...)
  npm run setup:carmen`)
  process.exit(0)
}

const child = spawn(python, process.argv.slice(2), { cwd: carmenDir, stdio: 'inherit' })
child.on('exit', (code) => process.exit(code ?? 1))
