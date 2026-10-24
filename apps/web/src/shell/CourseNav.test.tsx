import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import type { Course, Role } from '../api/types'
import { getCourseNavItems } from './courseTabs'
import CourseNav from './CourseNav'

const labels = (role: Role) => getCourseNavItems(role).map((t) => t.label)

const course = (role: Role): Course => ({
  id: 1,
  code: 'STAT 1450',
  name: 'Introduction to Statistical Reasoning',
  term: 'Autumn 2026',
  role,
})

describe('getCourseNavItems', () => {
  it('gives students Learning Insights and no Instructor Analytics', () => {
    expect(labels('student')).toContain('Learning Insights')
    expect(labels('student')).not.toContain('Instructor Analytics')
  })

  it('gives teachers Instructor Analytics and no Learning Insights', () => {
    expect(labels('teacher')).toContain('Instructor Analytics')
    expect(labels('teacher')).not.toContain('Learning Insights')
  })
})

describe('<CourseNav>', () => {
  it('renders no analytics link for a student', () => {
    render(
      <MemoryRouter initialEntries={['/courses/1']}>
        <CourseNav course={course('student')} />
      </MemoryRouter>,
    )
    expect(screen.getByRole('link', { name: 'Learning Insights' })).toHaveAttribute(
      'href',
      '/courses/1/insights',
    )
    expect(screen.queryByRole('link', { name: 'Instructor Analytics' })).toBeNull()
  })

  it('marks the current tab', () => {
    render(
      <MemoryRouter initialEntries={['/courses/1/grades']}>
        <CourseNav course={course('teacher')} />
      </MemoryRouter>,
    )
    expect(screen.getByRole('link', { name: 'Grades' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('link', { name: 'Home' })).not.toHaveAttribute('aria-current')
  })
})
