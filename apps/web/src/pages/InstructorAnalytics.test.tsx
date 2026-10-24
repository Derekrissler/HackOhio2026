import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Outlet, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Course } from '../api/types'
import { DemoUserProvider } from '../shell/demoUser'
import InstructorAnalytics from './InstructorAnalytics'

const course: Course = { id: 1, code: 'STAT 1450', name: 'Stats', term: null, role: 'student' }

function renderAs(userId: number, response: { status: number; body: unknown }) {
  const fetchMock = vi.fn(async () => new Response(JSON.stringify(response.body), { status: response.status }))
  vi.stubGlobal('fetch', fetchMock)
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <DemoUserProvider initialUserId={userId}>
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

  it('shows the placeholder for an instructor', async () => {
    renderAs(1, { status: 200, body: { course_id: 1, status: 'coming_in_phase_7' } })
    expect(await screen.findByText('Coming in Phase 7')).toBeInTheDocument()
    expect(screen.queryByText(/Access denied/)).toBeNull()
  })
})
