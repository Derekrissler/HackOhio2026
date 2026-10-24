import { IconButton, IconHamburgerLine, Spinner, View } from '@instructure/ui'
import { useState } from 'react'
import { Outlet, useOutletContext, useParams } from 'react-router-dom'

import { useCourse } from '../api/hooks'
import type { Course } from '../api/types'
import ApiErrorAlert from './ApiErrorAlert'
import Breadcrumbs from './Breadcrumbs'
import CourseNav from './CourseNav'

export default function CourseLayout() {
  const { courseId = '' } = useParams()
  const { data: course, error, isPending } = useCourse(courseId)
  const [navOpen, setNavOpen] = useState(true)

  if (isPending) {
    return (
      <View as="div" padding="large" textAlign="center">
        <Spinner renderTitle="Loading course" />
      </View>
    )
  }
  if (error) {
    return (
      <View as="div" padding="0 large">
        <ApiErrorAlert error={error} />
      </View>
    )
  }

  return (
    <>
      <header className="course-header">
        <IconButton
          screenReaderLabel={navOpen ? 'Hide course navigation' : 'Show course navigation'}
          withBackground={false}
          withBorder={false}
          onClick={() => setNavOpen((open) => !open)}
        >
          <IconHamburgerLine />
        </IconButton>
        <div className="course-header__crumbs">
          <Breadcrumbs course={course} />
        </div>
      </header>
      <div className="course-body">
        {navOpen && <CourseNav course={course} />}
        <div className="course-content">
          <Outlet context={course} />
        </div>
      </div>
    </>
  )
}

/** The current course, for pages rendered inside <CourseLayout>. */
export const useCurrentCourse = () => useOutletContext<Course>()
