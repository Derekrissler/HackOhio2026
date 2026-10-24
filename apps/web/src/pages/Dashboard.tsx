import { Heading, Spinner, Text, View } from '@instructure/ui'
import { Link } from 'react-router-dom'

import { useCourses } from '../api/hooks'
import type { Course } from '../api/types'
import ApiErrorAlert from '../shell/ApiErrorAlert'
import { courseColors } from '../theme'
import { useDocumentTitle } from './PlaceholderPage'

export default function Dashboard() {
  const { data: courses, error, isPending } = useCourses()
  useDocumentTitle('Dashboard')

  return (
    <View as="div" padding="medium large">
      <View as="div" borderWidth="0 0 small 0" padding="0 0 small" margin="0 0 large">
        <Heading level="h1">Dashboard</Heading>
      </View>
      {isPending ? (
        <Spinner renderTitle="Loading courses" />
      ) : error ? (
        <ApiErrorAlert error={error} />
      ) : courses.length === 0 ? (
        <Text>You are not enrolled in any courses.</Text>
      ) : (
        <ul className="course-cards" aria-label="Courses">
          {courses.map((course, i) => (
            <li key={course.id}>
              <CourseCard course={course} color={courseColors[i % courseColors.length]} />
            </li>
          ))}
        </ul>
      )}
    </View>
  )
}

function CourseCard({ course, color }: { course: Course; color: string }) {
  return (
    <Link className="course-card" to={`/courses/${course.id}`}>
      <div className="course-card__hero" style={{ background: color }} aria-hidden="true" />
      <div className="course-card__body">
        <span className="course-card__name" style={{ color }}>
          {course.name}
        </span>
        <span className="course-card__meta">{course.code}</span>
        {course.term && <span className="course-card__meta">{course.term}</span>}
      </div>
    </Link>
  )
}
