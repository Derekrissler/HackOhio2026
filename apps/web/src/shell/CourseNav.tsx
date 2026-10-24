import { NavLink } from 'react-router-dom'

import type { Course } from '../api/types'
import { getCourseNavItems } from './courseTabs'

export default function CourseNav({ course }: { course: Course }) {
  return (
    <nav className="course-nav" aria-label="Course navigation">
      <ul>
        {getCourseNavItems(course.role).map((tab) => (
          <li key={tab.path}>
            {/* Only Home needs an exact match; detail pages (assignments/12) keep their tab lit. */}
            <NavLink to={`/courses/${course.id}/${tab.path}`.replace(/\/$/, '')} end={tab.path === ''}>
              {tab.label}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  )
}
