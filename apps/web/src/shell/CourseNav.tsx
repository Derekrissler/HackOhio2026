import { NavLink } from 'react-router-dom'

import type { Course } from '../api/types'
import { getCourseNavItems } from './courseTabs'

export default function CourseNav({ course }: { course: Course }) {
  return (
    <nav className="course-nav" aria-label="Course navigation">
      <ul>
        {getCourseNavItems(course.role).map((tab) => (
          <li key={tab.path}>
            <NavLink to={`/courses/${course.id}/${tab.path}`.replace(/\/$/, '')} end>
              {tab.label}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  )
}
