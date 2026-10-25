import { fireEvent, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { URL as NodeURL } from 'node:url'

const script = readFileSync(new NodeURL('../../../../carmen-study-guide/mock-canvas/static/tutor.js', import.meta.url), 'utf8')

function setup() {
  document.body.innerHTML = `<div class="tutor" data-course="1001">
    <div class="tutor-notice"></div><form id="tutor-login-form">
    <label>Email<input name="email" type="email" required></label>
    <label>Password<input name="password" type="password" required></label>
    <button type="submit">Sign in</button></form><button id="tutor-signout" hidden>Sign out</button>
    <select id="tutor-assessment"></select><div id="tutor-log"></div>
    <form id="tutor-form"><textarea id="tutor-input"></textarea><button type="submit">Send</button></form></div>`
  window.eval(script)
}
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })
async function signIn() {
  const user = userEvent.setup()
  await user.type(screen.getByLabelText('Email'), 'fictional@example.invalid')
  await user.type(screen.getByLabelText('Password'), 'fictional-password')
  await user.click(screen.getByRole('button', { name: 'Sign in' }))
  await waitFor(() => expect(screen.getByRole('button', { name: 'Send' })).toBeEnabled())
  return user
}
afterEach(() => { vi.unstubAllGlobals(); document.body.replaceChildren() })

describe('Carmen tutor authentication', () => {
  it('requires sign-in, sends same-origin requests and clears the display on logout', async () => {
    let authenticated = false
    const fetcher = vi.fn(async (url: string) => {
      if (url.endsWith('/auth/login')) { authenticated = true; return response({ signed_in: true }) }
      if (url.endsWith('/auth/logout')) { authenticated = false; return response({ signed_in: false }) }
      return authenticated ? response({ assessments: [{ id: 'fictional-assessment', title: 'Assignment', mode: 'guided_homework' }] }) : response({}, 401)
    })
    vi.stubGlobal('fetch', fetcher)
    setup()
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled()
    const user = await signIn()
    expect(fetcher).toHaveBeenCalledWith('/courses/1001/tutor/auth/login', expect.objectContaining({
      headers: { 'Content-Type': 'application/json', 'X-Tutor-Request': '1' },
    }))
    expect(screen.getByLabelText('Password')).toHaveValue('')
    document.getElementById('tutor-log')!.textContent = 'Previous user content'
    await user.click(screen.getByRole('button', { name: 'Sign out' }))
    expect(screen.queryByText('Previous user content')).toBeNull()
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled()
  })

  it('ignores an old unauthenticated context response after a successful sign-in', async () => {
    let resolveFirst: (response: Response) => void = () => {}
    let calls = 0
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.endsWith('/auth/login')) return response({ signed_in: true })
      calls++
      if (calls === 1) return new Promise<Response>(resolve => { resolveFirst = resolve })
      return response({ assessments: [] })
    }))
    setup()
    await signIn()
    resolveFirst(response({}, 401))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Send' })).toBeEnabled())
  })

  it('keeps sign-out available for retry after a network failure', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.endsWith('/auth/logout')) throw new Error('network unavailable')
      if (url.endsWith('/auth/login')) return response({ signed_in: true })
      return response({ assessments: [] })
    }))
    setup()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Send' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))
    expect(await screen.findByText(/Retry signing out/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sign out' })).toBeVisible()
  })
})
