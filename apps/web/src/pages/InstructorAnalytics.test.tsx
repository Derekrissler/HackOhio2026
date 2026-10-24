import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Outlet, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { AnalyticsDashboard, Course } from '../api/types'
import { DemoUserProvider, useDemoUser } from '../shell/demoUser'
import InstructorAnalytics, { Dashboard } from './InstructorAnalytics'

const auth = vi.hoisted(() => ({
  listener: undefined as undefined | ((event: string, session: unknown) => void),
  onAuthStateChange: vi.fn(), signInWithPassword: vi.fn(), signOut: vi.fn(),
  stopAutoRefresh: vi.fn(), startAutoRefresh: vi.fn(),
}))
vi.mock('../api/supabase', () => ({ createAnalyticsClient: () => ({ auth }) }))

beforeEach(() => {
  vi.clearAllMocks()
  auth.listener = undefined
  auth.onAuthStateChange.mockImplementation(listener => {
    auth.listener = listener
    return { data: { subscription: { unsubscribe: vi.fn() } } }
  })
  auth.signInWithPassword.mockImplementation(async () => {
    auth.listener?.('SIGNED_IN', { access_token: 'fictional-user-token' })
    return { error: null }
  })
  auth.signOut.mockImplementation(async () => { auth.listener?.('SIGNED_OUT', null) })
})

const course: Course = { id: 1, code: 'STAT 1450', name: 'Stats', term: null, role: 'student' }

function SwitchDemoUser() {
  const { setUserId } = useDemoUser()
  return <button onClick={() => setUserId(10)}>Switch demo user</button>
}

function renderAs(userId: number, response: { status: number; body: unknown }, live?: Record<string, unknown>) {
  const fetchMock = vi.fn(async (path: string) => new Response(JSON.stringify(live?.[path] ?? response.body), { status: response.status }))
  vi.stubGlobal('fetch', fetchMock)
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <DemoUserProvider initialUserId={userId}>
        <SwitchDemoUser />
        <MemoryRouter initialEntries={['/courses/1/analytics']}>
          <Routes>
            <Route path="/courses/:courseId" element={<Outlet context={course} />}>
              <Route path="analytics" element={<InstructorAnalytics />} />
            </Route>
          </Routes>
        </MemoryRouter>
      </DemoUserProvider>
    </QueryClientProvider>,
  )
  return fetchMock
}

afterEach(() => vi.unstubAllGlobals())

describe('<InstructorAnalytics>', () => {
  it('shows Access denied when the API answers 403', async () => {
    const fetchMock = renderAs(2, { status: 403, body: { detail: 'Instructors only' } })
    expect(await screen.findByText(/Access denied/)).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/courses/1/analytics/summary', {
      headers: { 'X-Demo-User': '2' },
    })
  })

  it('requires separate course-account sign-in for an instructor', async () => {
    renderAs(1, { status: 200, body: { course_id: 1, status: 'supabase_sign_in_required' } })
    expect(await screen.findByRole('button', { name: 'Sign in to analytics' })).toBeInTheDocument()
    expect(screen.queryByText(/Access denied/)).toBeNull()
  })

  it('signs in and reads the selected UUID course with a bearer token', async () => {
    const user = userEvent.setup()
    const fetchMock = renderAs(1, { status: 200, body: { course_id: 1, status: 'supabase_sign_in_required' } }, {
      '/api/analytics/courses': [{ id: 'fictional-course-uuid', code: 'TEST101', title: 'Fictional course', canvas_id: '1', role: 'instructor' }],
      '/api/analytics/courses/fictional-course-uuid/summary': dashboard,
    })
    await user.type(await screen.findByLabelText('Email'), 'teacher@example.invalid')
    await user.type(screen.getByLabelText('Password'), 'fictional-password')
    await user.click(screen.getByRole('button', { name: 'Sign in to analytics' }))
    expect(await screen.findByRole('region', { name: 'Published analytics' })).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/analytics/courses/fictional-course-uuid/summary', expect.objectContaining({
      headers: { Authorization: 'Bearer fictional-user-token' }, cache: 'no-store',
    }))
    expect(screen.getByText('60.0%')).toBeInTheDocument()
    expect(screen.getByText('75.0%')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Sign out' }))
    expect(await screen.findByRole('button', { name: 'Sign in to analytics' })).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Published analytics' })).toBeNull()
    expect(auth.signOut).toHaveBeenCalledWith({ scope: 'local' })
  })

  it('does not retain displayed results when the demo identity changes', async () => {
    const user = userEvent.setup()
    renderAs(1, { status: 200, body: { course_id: 1, status: 'supabase_sign_in_required' } }, {
      '/api/analytics/courses': [{ id: 'fictional-course-uuid', code: 'TEST101', title: 'Fictional course', canvas_id: '1', role: 'instructor' }],
      '/api/analytics/courses/fictional-course-uuid/summary': dashboard,
    })
    await user.type(await screen.findByLabelText('Email'), 'teacher@example.invalid')
    await user.type(screen.getByLabelText('Password'), 'fictional-password')
    await user.click(screen.getByRole('button', { name: 'Sign in to analytics' }))
    await screen.findByRole('region', { name: 'Published analytics' })
    await user.click(screen.getByRole('button', { name: 'Switch demo user' }))
    expect(await screen.findByRole('button', { name: 'Sign in to analytics' })).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Published analytics' })).toBeNull()
  })

  it('does not guess a course UUID when the Canvas ID has no match', async () => {
    const user = userEvent.setup()
    const fetchMock = renderAs(1, { status: 200, body: { course_id: 1, status: 'supabase_sign_in_required' } }, {
      '/api/analytics/courses': [{ id: 'fictional-other-uuid', code: 'TEST102', title: 'Other course', canvas_id: '200', role: 'instructor' }],
    })
    await user.type(await screen.findByLabelText('Email'), 'teacher@example.invalid')
    await user.type(screen.getByLabelText('Password'), 'fictional-password')
    await user.click(screen.getByRole('button', { name: 'Sign in to analytics' }))
    expect(await screen.findByRole('combobox', { name: 'Analytics course' })).toHaveValue('')
    expect(fetchMock.mock.calls.some(([path]) => path.endsWith('/summary') && path.includes('fictional-other'))).toBe(false)
  })

  it('shows a safe sign-in failure', async () => {
    auth.signInWithPassword.mockResolvedValue({ error: { message: 'private diagnostic' } })
    const user = userEvent.setup()
    renderAs(1, { status: 200, body: { course_id: 1, status: 'supabase_sign_in_required' } })
    await user.type(await screen.findByLabelText('Email'), 'teacher@example.invalid')
    await user.type(screen.getByLabelText('Password'), 'fictional-password')
    await user.click(screen.getByRole('button', { name: 'Sign in to analytics' }))
    expect(await screen.findByText(/Sign-in failed/)).toBeInTheDocument()
    expect(screen.queryByText('private diagnostic')).toBeNull()
    expect(screen.getByLabelText('Password')).toHaveValue('')
  })
})

const dashboard: AnalyticsDashboard = {
  course_id: 'fictional-course-uuid', status: 'ready', run_id: 'fictional-run', computed_at: '2026-10-24T18:00:00Z',
  interpretation: 'Descriptive performance, not mastery.', clusters: [],
  performance: [{
    id: 'fictional-arr', scope: 'class_outcome', outcome_id: 'fictional-outcome', assessment_id: null, question_id: null,
    label: 'LO-1', mean_student_ratio: .6, pooled_score_ratio: .75, observed_score_ratio: null,
    eligible_students: 10, assessed_students: 12, evidence_coverage_ratio: null, score_observations: null,
    evidence_count: 24, insufficient_evidence: false, suppressed: false,
  }],
}

describe('published analytics display', () => {
  it.each(['stale', 'incomplete', 'no_results'] as const)('hides metrics when status is %s', status => {
    render(<Dashboard data={{ ...dashboard, status }} />)
    expect(screen.queryByText('60.0%')).toBeNull()
    expect(screen.queryByText('LO-1')).toBeNull()
  })
  it('shows unknown coverage without converting it to zero', () => {
    render(<Dashboard data={dashboard} />)
    expect(screen.getByText('Unavailable')).toBeInTheDocument()
    expect(screen.queryByText('0.0%')).toBeNull()
  })
  it('hides suppressed measurements even if a response accidentally supplies values', () => {
    render(<Dashboard data={{ ...dashboard, performance: dashboard.performance.map(row => ({ ...row, suppressed: true })) }} />)
    expect(screen.getByText('Small cohort suppressed')).toBeInTheDocument()
    expect(screen.queryByText('60.0%')).toBeNull()
    expect(screen.queryByText('75.0%')).toBeNull()
  })
})
